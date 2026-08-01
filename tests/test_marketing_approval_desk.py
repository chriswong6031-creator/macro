"""tests/test_marketing_approval_desk.py — the autonomous approval desk.

WHAT THIS PINS. `engine/marketing/approval_desk.py` is the machine form of the
operator instruction "closely audit them, then approve them so they go out
quickly without me". It is the only path to live for the nine planned kinds:
`data/marketing/outbox/decisions.jsonl` (the designed operator-approve path)
has ZERO rows in repo history, so before this desk every planned post that ever
reached X was hand-transitioned by an agent session.

A gate with that much authority has to be pinned by OUTCOME, not by call count.
Every test below asserts the ledger status an item actually reaches and the
CHECK NAME recorded in its note, because the note is the operator's only handle
on "why did the desk do that".

Layout:
  1. behavioural matrix — one item per verdict class, `audit_item` only (pure)
  2. the sweep — `run()`: cap, kill switch, human decisions, dry-run
  3. publisher integration — a planned item goes queued → approved → dispatched
     in ONE sweep, while the breaking and mover lanes are untouched
  4. the Floor — every desk counter carries plain words and lands in the right
     ledger half
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest


_NOW = datetime(2026, 7, 31, 16, 0, 0, tzinfo=timezone.utc)
_AS_OF = "2026-07-31"

#: A signal that can prove everything it says: entry + invalidation in its
#: source, both levels printed verbatim, a hosted chart, one cashtag.
_CLEAN_TEXT = ("$PLTR reclaimed 190 and has held it for six sessions. "
               "Entry 190, out below 178.5.")
_CLEAN_SOURCE = {"ticker": "PLTR", "entry": 190.0, "invalidation": 178.5,
                 "media_url": "https://r2.example/marketing/charts/pltr.png"}


def _item(**kw) -> dict:
    """A minimal outbox-shaped item dict. Overridable field by field."""
    base = {
        "schema": "marketing.outbox/v1",
        "id": "ob-2026-07-31-test000001",
        "as_of": _AS_OF,
        "account": "flagship",
        "kind": "signal",
        "text": _CLEAN_TEXT,
        "media": [],
        "scheduled_at": "immediate",
        "slot": None,
        "priority": 5,
        "provenance": "content_studio",
        "source": dict(_CLEAN_SOURCE),
        "status": "queued",
        "created_at": "2026-07-31T04:00:00Z",
    }
    base.update(kw)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# 1. Behavioural matrix — one item per verdict class
# ─────────────────────────────────────────────────────────────────────────────

class TestBehaviouralMatrix:

    def test_a_provable_signal_is_approved_with_every_check_named(self):
        """The happy path, and the note the operator will read afterwards.

        PINS: `action == "approve"` AND all six check names in `passed` — an
        approve whose note lists four checks would mean two of them silently
        stopped running, which is how a gate rots into decoration.
        """
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(), now=_NOW)
        assert v.action == "approve", (v.check, v.evidence)
        assert set(v.passed) == {"payload", "number_sanity", "liveness",
                                 "chart_law", "banned_language", "dedup"}, v.passed

    def test_zero_payload_education_quarantines_naming_payload(self):
        """THE ZERO-PAYLOAD EDUCATION DEFECT, enforced at post time forever.

        "The discipline a watch list enforces" is a hook, a promise of a lesson,
        and nothing a reader could check, disagree with or act on. It cleared
        every gate in the stack because every gate screened what a post SAYS and
        none screened whether it said anything.

        PINS: `action == "quarantine"` AND `check == "payload"` — the name is
        the assertion. A quarantine under any other check name would mean the
        payload floor is not what caught it, and the defect could walk back in
        through a post that happens to trip a different gate today.
        """
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(kind="education", source={},
                             text="The discipline a watch list enforces."),
                       now=_NOW)
        assert v.action == "quarantine"
        assert v.check == "payload", v
        assert "no number, cashtag or dated precedent" in v.evidence

    @pytest.mark.parametrize("text", [
        "Macro without the jargon.",
        "The base-rate way of thinking.",
        "Using analogues without kidding yourself.",
        "How I keep myself honest.",
    ])
    def test_every_measured_zero_payload_stem_quarantines(self, text):
        """The other four bare stems from the value-gate corpus, by name."""
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(kind="education", source={}, text=text), now=_NOW)
        assert (v.action, v.check) == ("quarantine", "payload"), (text, v)

    def test_a_number_alone_satisfies_the_payload_floor(self):
        """The floor is "does this post make a claim", NOT "is it good".

        PINS the other side of the payload check: a breadth read with no cashtag
        and no date still carries a falsifiable number, so payload must PASS it
        (the item is held later for want of evidence, which is a different and
        non-terminal verdict). A payload check that also demanded a ticker would
        quarantine the desks' entire non-ticker voice.
        """
        from engine.marketing.approval_desk import check_payload

        c = check_payload("Breadth is wide today: 231 of 231 names above the "
                          "200 day line.")
        assert c.status == "pass", c

    def test_an_invented_228_style_target_quarantines_naming_invented_level(self):
        """THE $TPR-228 FABRICATION: a chart FACT promoted to a price objective.

        The item's plan gave it entry 190 and invalidation 178. Nothing gave it
        228 — that number was a legitimate 52-week-high fact sitting in the
        writer's whitelist, and asking a reader to aim at it is the fabrication.

        PINS: quarantine under `invented_level` specifically, not under
        `implausible_target` (228 from 190 is +20%, inside the swing bar) —
        the two hard fails must stay separable, because one says "that number
        is not yours" and the other says "that number is not possible".
        """
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(text="$TPR held 190 all week. Targeting 228 next.",
                             source={"ticker": "TPR", "entry": 190.0,
                                     "invalidation": 178.0,
                                     "media_url": "https://r2.example/t.png"}),
                       now=_NOW)
        assert v.action == "quarantine"
        assert v.check == "invented_level", v
        assert "228" in v.evidence

    def test_an_implausible_target_quarantines_even_when_traceable(self):
        """A target can trace and still be a lottery ticket.

        Measured shape, from the live queue: "$LPG at 43.91 ... Target 68.41" —
        +55.8% over a 2-4 week swing horizon.

        PINS: `implausible_target` fires from the post's OWN quoted price when
        the item carries no entry, i.e. the check does not need a fact packet to
        do its job. Without that, the exact post that motivated the rule would
        have landed in the (non-terminal) unverifiable bucket instead.
        """
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(text="$LPG at 43.91. Simple read. Target 68.41, "
                                  "out below 27.58.",
                             source={"ticker": "LPG",
                                     "media_url": "https://r2.example/l.png"}),
                       now=_NOW)
        assert v.action == "quarantine"
        assert v.check == "implausible_target", v
        assert "+55.8%" in v.evidence

    def test_a_target_inside_the_bar_is_not_flagged(self):
        """Mutation guard for the check above: +7.9% must NOT fire.

        Without this, an `abs(...) > 35` accidentally written as `> 0` would
        pass the failing test above and quarantine every target on the board.
        """
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(text="$PLTR at 190. Entry 190, out below 178.5, "
                                  "targeting 205.",
                             source=dict(_CLEAN_SOURCE, t1=205.0)),
                       now=_NOW)
        assert v.action == "approve", (v.check, v.evidence)

    def test_a_packetless_item_is_held_not_approved_and_not_killed(self):
        """THE CONSERVATIVE DEFAULT — the whole safety argument in one test.

        A macro post carries numbers and its `source` carries nothing (measured:
        macro / education / event / insider rows in
        `data/marketing/outbox/items.jsonl` hold only plan_item_id, chart_id and
        the value-gate stamp). The desk has nothing to check the numbers
        against.

        PINS BOTH HALVES: not `approve` (autonomy must never bless what it
        cannot verify) and not `quarantine` (an unprovable post is a post the
        operator should see, not one the machine should destroy). Either half
        failing alone is a different, worse desk.
        """
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(kind="macro", source={},
                             text="Breadth is wide today: 231 of 231 names "
                                  "above the 200 day line."),
                       now=_NOW)
        assert v.action == "hold", v
        assert v.check == "number_sanity"
        assert "no fact evidence" in v.evidence

    def test_an_expired_slot_quarantines_naming_expired(self):
        """A post whose ladder slot is six days old describes a dead tape."""
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(scheduled_at="2026-07-25T14:00:00Z"), now=_NOW)
        assert v.action == "quarantine"
        assert v.check == "expired", v
        assert "36h TTL" in v.evidence

    def test_an_unparseable_slot_is_never_expired(self):
        """A malformed stamp must not be the reason a post is destroyed."""
        from engine.marketing.approval_desk import check_liveness

        c = check_liveness(_item(scheduled_at="tomorrow-ish"), now=_NOW,
                           ttl_hours=36)
        assert c.status == "pass", c

    def test_a_chartless_ticker_post_is_HELD_not_quarantined(self):
        """SOFT HOLD, and the softness is the point.

        A missing `media_url` is usually an R2 upload race that
        `scripts/marketing_media_backfill.py` heals hours later. The publisher's
        own `_missing_required_media` DEFERS for exactly that reason. A desk
        that quarantined here would terminally destroy a post the backfill was
        about to fix.

        PINS: `hold` under `chart_law`. Asserting merely "not approved" would
        pass just as happily on a quarantine, which is the bug.
        """
        from engine.marketing.approval_desk import audit_item

        src = dict(_CLEAN_SOURCE)
        src.pop("media_url")
        v = audit_item(_item(source=src), now=_NOW)
        assert v.action == "hold", v
        assert v.check == "chart_law", v

    def test_chart_law_is_inert_when_media_is_globally_off(self):
        """With publish.media_enabled off NOTHING can resolve a URL, so holding
        on one would wedge every ticker post instead of one."""
        from engine.marketing.approval_desk import audit_item

        src = dict(_CLEAN_SOURCE)
        src.pop("media_url")
        v = audit_item(_item(source=src), now=_NOW, media_enabled=False)
        assert v.action == "approve", (v.check, v.evidence)

    def test_a_non_ticker_kind_owes_no_picture(self):
        """macro / education / event are not chart-bearing kinds — the KIND
        decides, not the text (the contract stated at _TICKER_ROLLUP_KINDS)."""
        from engine.marketing.approval_desk import check_chart_law

        assert check_chart_law(_item(kind="macro", media=[], source={}),
                               media_enabled=True).status == "pass"

    def test_banned_language_quarantines_through_the_house_list(self):
        """THE QUEUE IS A BYPASS AROUND EVERY GENERATION LAW.

        Copy enqueued by a lane that predated a ban fires days later where no
        generation-time validator can reach it (the 2026-07-27 "$AVGO POC held"
        post). The desk re-scans through `copywriter.banned_language` — the same
        function, never a re-implemented list — before it blesses anything.
        """
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(text="$PLTR reclaimed 190 — entry 190, out below "
                                  "178.5."),
                       now=_NOW)
        assert v.action == "quarantine"
        assert v.check == "banned_language", v
        assert "em dash" in v.evidence

    def test_a_near_duplicate_of_a_recent_post_quarantines(self):
        """Same content as something this account posted this week."""
        from engine.marketing.approval_desk import audit_item

        posted = {"flagship": [(
            "ob-2026-07-29-aaaaaaaaaa",
            "$PLTR reclaimed 190 and has held it for six sessions. Entry 190, "
            "out below 178.5.",
            "2026-07-29")]}
        v = audit_item(_item(), now=_NOW, posted_texts=posted)
        assert v.action == "quarantine"
        assert v.check == "near_dup", v
        assert "jaccard=1.00" in v.evidence

    def test_a_deeply_reworded_post_is_not_a_near_duplicate(self):
        """Mutation guard: the bar is 0.85, not "any overlap"."""
        from engine.marketing.approval_desk import audit_item

        posted = {"flagship": [(
            "ob-2026-07-29-aaaaaaaaaa",
            "Rate expectations shifted again and the long end took the brunt "
            "of it through the afternoon.",
            "2026-07-29")]}
        v = audit_item(_item(), now=_NOW, posted_texts=posted)
        assert v.action == "approve", (v.check, v.evidence)

    def test_dedup_is_strictly_per_account(self):
        """A sibling desk covering the same story is sentinel's plan-time job at
        a stricter bar, not this desk's."""
        from engine.marketing.approval_desk import audit_item

        posted = {"sophia": [("ob-x", _CLEAN_TEXT, "2026-07-29")]}
        v = audit_item(_item(), now=_NOW, posted_texts=posted)
        assert v.action == "approve", (v.check, v.evidence)

    def test_a_hard_fail_outranks_a_soft_hold(self):
        """An item that is BOTH chartless and payload-free is quarantined.

        PINS the resolution order in `audit_item`: hard fails are scanned before
        holds. Reversed, a post with no payload would sit queued forever behind
        a chart that is never coming.
        """
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(text="Watching this one closely.", source={}),
                       now=_NOW)
        assert (v.action, v.check) == ("quarantine", "payload"), v


# ─────────────────────────────────────────────────────────────────────────────
# 2. The sweep — run()
# ─────────────────────────────────────────────────────────────────────────────

#: `now` for a STALE seed. `outbox.apply_schedule_floor` clamps a scheduled_at
#: that predates the item's own created_at forward to creation time, so an item
#: cannot be born already late — a stale-slot fixture has to be BORN before its
#: slot, exactly as the nightly emit creates it.
_BORN_EARLY = datetime(2026, 7, 25, 4, 0, 0, tzinfo=timezone.utc)


def _seed(tmp_path: Path, *, kind: str = "signal", text: str = _CLEAN_TEXT,
          account: str = "flagship", provenance: str = "content_studio",
          source: dict | None = None, scheduled_at: str = "immediate",
          now: datetime | None = None) -> str:
    from engine.marketing.outbox import enqueue, make_item

    born = now or (_BORN_EARLY if scheduled_at not in ("immediate", "") else _NOW)
    item = make_item(account=account, kind=kind, text=text, as_of=_AS_OF,
                     scheduled_at=scheduled_at, provenance=provenance,
                     source=dict(_CLEAN_SOURCE) if source is None else source,
                     now=born)
    code = enqueue(item, root=tmp_path, max_per_account_day=999)
    assert code == "queued", (code, text[:60])
    assert item["scheduled_at"] == scheduled_at, (
        "the fixture was clamped forward — a stale-slot test that silently "
        "seeds a FRESH slot proves nothing")
    return item["id"]


class TestTheSweep:

    def test_the_kill_switch_no_ops_and_the_tally_says_disabled(self, tmp_path):
        """CONFIG IS THE KILL SWITCH. `enabled: false` → the desk touches
        nothing and SAYS SO.

        PINS both: the item is still `queued` (no transition), and
        `tally["status"] == "disabled"`. Without the second assertion a desk
        that crashed on import would look identical to one an operator switched
        off, which is the difference between a config decision and an outage.
        """
        from engine.marketing import approval_desk as desk
        from engine.marketing.outbox import current_statuses, read_ledger

        iid = _seed(tmp_path)
        tally = desk.run(tmp_path, cfg={"approval_desk": {"enabled": False}},
                         now=_NOW, live=True)
        assert tally["status"] == "disabled"
        assert tally["approved"] == 0 and tally["quarantined"] == 0
        assert current_statuses(tmp_path)[iid] == "queued"
        assert read_ledger(tmp_path) == []

    def test_a_missing_config_block_still_arms_the_desk(self, tmp_path):
        """Deleting the key must not silently disarm a desk the operator asked
        for — only an explicit `enabled: false` turns it off."""
        from engine.marketing import approval_desk as desk

        iid = _seed(tmp_path)
        tally = desk.run(tmp_path, cfg={}, now=_NOW, live=True)
        assert tally["status"] == "ran"
        assert tally["approved_ids"] == [iid]

    def test_the_per_sweep_cap_approves_40_and_leaves_the_41st_queued(self, tmp_path):
        """41 eligible → 40 approved, 1 capped, and the counter says which.

        WHY A CAP AT ALL: a measured nightly plan is ~218 items across seven
        desks. Approving all of them in one sweep hands the dispatch loop a
        backlog that the daily caps and the 4-minute spacing floor then meter
        out over DAYS — queue order decides what ships and the freshest reads
        sit behind the stalest. The overflow is not rejected: it stays `queued`
        and is re-audited next sweep against fresher evidence.
        """
        from engine.marketing import approval_desk as desk
        from engine.marketing.outbox import current_statuses

        ids = []
        for i in range(41):
            price = 100 + i
            ids.append(_seed(
                tmp_path,
                text=f"$AA{i:02d} reclaimed {price} and held it. "
                     f"Entry {price}, out below {price - 9}.",
                source={"ticker": f"AA{i:02d}", "entry": float(price),
                        "invalidation": float(price - 9),
                        "media_url": f"https://r2.example/{i}.png"}))

        tally = desk.run(tmp_path, cfg={"approval_desk": {}}, now=_NOW, live=True)
        assert tally["approved"] == 40, tally
        assert tally["capped"] == 1, tally
        assert len(tally["capped_ids"]) == 1

        statuses = current_statuses(tmp_path)
        approved = [i for i in ids if statuses[i] == "approved"]
        queued = [i for i in ids if statuses[i] == "queued"]
        assert len(approved) == 40 and len(queued) == 1
        assert queued == tally["capped_ids"]

    def test_an_operator_hold_is_never_approved_by_the_desk(self, tmp_path):
        """THE decisions.jsonl PATH OUTRANKS THE DESK.

        A `hold` is the operator saying "not yet". The desk must leave it alone
        even when every check passes — otherwise the one control the operator
        has over an autonomous lane is a control the lane ignores.
        """
        from engine.marketing import approval_desk as desk
        from engine.marketing.outbox import current_statuses, record_decision

        iid = _seed(tmp_path)
        assert record_decision(iid, "hold", actor="operator", root=tmp_path)

        tally = desk.run(tmp_path, cfg={}, now=_NOW, live=True)
        assert tally["considered"] == 0, tally
        assert tally["approved"] == 0
        assert current_statuses(tmp_path)[iid] == "queued"

    def test_an_operator_approve_is_left_to_the_actuator(self, tmp_path):
        """The other direction: an item the operator already cleared is the
        actuator's (`outbox.apply_decisions`) to transition, not the desk's."""
        from engine.marketing import approval_desk as desk
        from engine.marketing.outbox import record_decision

        iid = _seed(tmp_path)
        assert record_decision(iid, "approve", actor="operator", root=tmp_path)

        tally = desk.run(tmp_path, cfg={}, now=_NOW, live=True)
        assert tally["considered"] == 0, tally
        assert iid not in tally["approved_ids"]

    def test_dry_run_writes_no_ledger_rows(self, tmp_path):
        """A projection must not destroy the queue it is projecting.

        PINS byte-equality of the ledger across a dry-run sweep that WOULD have
        approved one item and quarantined another — the tally reports both and
        the disk is untouched.
        """
        from engine.marketing import approval_desk as desk
        from engine.marketing.outbox import _ledger_path

        good = _seed(tmp_path)
        bad = _seed(tmp_path, kind="education", source={},
                    text="Macro without the jargon.")
        ledger = _ledger_path(tmp_path)
        before = ledger.read_bytes() if ledger.exists() else b""

        tally = desk.run(tmp_path, cfg={}, now=_NOW, live=False)
        assert tally["approved_ids"] == [good]
        assert tally["quarantined_ids"] == [bad]
        after = ledger.read_bytes() if ledger.exists() else b""
        assert after == before

    def test_the_note_names_the_checks_that_passed(self, tmp_path):
        """The ledger note is the operator's receipt. It has to be readable
        without opening the code: `approval-desk: payload, number_sanity, …`."""
        from engine.marketing import approval_desk as desk
        from engine.marketing.outbox import read_ledger

        iid = _seed(tmp_path)
        desk.run(tmp_path, cfg={}, now=_NOW, live=True)
        row = [r for r in read_ledger(tmp_path) if r["id"] == iid][-1]
        assert row["to"] == "approved"
        assert row["actor"] == "approval-desk"
        assert row["note"].startswith("approval-desk: ")
        for name in ("payload", "number_sanity", "liveness", "chart_law",
                     "banned_language", "dedup"):
            assert name in row["note"], row["note"]

    def test_a_quarantine_note_carries_the_check_and_the_evidence(self, tmp_path):
        from engine.marketing import approval_desk as desk
        from engine.marketing.outbox import current_statuses, read_ledger

        iid = _seed(tmp_path, kind="education", source={},
                    text="The discipline a watch list enforces.")
        desk.run(tmp_path, cfg={}, now=_NOW, live=True)
        assert current_statuses(tmp_path)[iid] == "quarantined"
        row = [r for r in read_ledger(tmp_path) if r["id"] == iid][-1]
        assert row["note"].startswith("approval-desk: payload: "), row["note"]

    def test_the_desk_reuses_expire_stale_planned_for_the_covered_set(self, tmp_path):
        """LIVENESS IS A REUSE, NOT A SECOND REAPER.

        `outbox.expire_stale_planned` is the repo's one writer for "a planned
        item sat past its slot", and until this desk it ran ONLY at nightly
        emit — nothing swept the queue during the trading day. The desk calls
        it, so the retirement carries that function's own note.

        PINS the note text, which is what distinguishes the reused reaper from
        a duplicate one the desk grew for itself.
        """
        from engine.marketing import approval_desk as desk
        from engine.marketing.outbox import current_statuses, read_ledger

        iid = _seed(tmp_path, scheduled_at="2026-07-25T14:00:00Z")
        tally = desk.run(tmp_path, cfg={}, now=_NOW, live=True)
        assert tally["expired"] == 1, tally
        assert current_statuses(tmp_path)[iid] == "quarantined"
        row = [r for r in read_ledger(tmp_path) if r["id"] == iid][-1]
        assert row["actor"] == "approval-desk"
        assert row["note"] == "expired: superseded by tonight's plan"

    def test_the_desk_expires_a_planned_lane_the_reaper_cannot_reach(self, tmp_path):
        """THE GAP THIS FILLS. `expire_stale_planned` is scoped to
        `content_studio` provenance. The weekend_levels watchlist lane (22 rows
        in the measured corpus, carrying state / last_close / wk_pct) is a
        planned kind on a real ladder slot and was swept by NOBODY.

        PINS: a stale `weekend_levels` item is quarantined under the desk's own
        `expired` check — the reaper above leaves it alone, so a test that only
        covered content_studio would pass on a desk that never closed the gap.
        """
        from engine.marketing import approval_desk as desk
        from engine.marketing.outbox import current_statuses, read_ledger

        iid = _seed(tmp_path, provenance="weekend_levels",
                    scheduled_at="2026-07-25T14:00:00Z")
        tally = desk.run(tmp_path, cfg={}, now=_NOW, live=True)
        assert tally["expired"] == 0, "the content_studio reaper must not take it"
        assert tally["quarantined"] == 1, tally
        assert current_statuses(tmp_path)[iid] == "quarantined"
        row = [r for r in read_ledger(tmp_path) if r["id"] == iid][-1]
        assert row["note"].startswith("approval-desk: expired: "), row["note"]

    def test_out_of_scope_kinds_are_never_considered(self, tmp_path):
        """`breaking` has its own all-gates-passed immediate path; `mover` and
        `theme_list` are already cleared by kind-scoped auto-approve seconds
        after generation. The desk must not touch any of them."""
        from engine.marketing import approval_desk as desk
        from engine.marketing.outbox import current_statuses

        ids = [
            _seed(tmp_path, kind="breaking", provenance="press_lane",
                  source={"lane": "press"},
                  text="Fed holds rates steady at 4.25%, third meeting running."),
            _seed(tmp_path, kind="mover", provenance="publisher_live_movers",
                  source={"ticker": "NVDA", "baseline_pct": 4.2},
                  text="$NVDA up 4.2% on the session, leading the tape higher."),
        ]
        tally = desk.run(tmp_path, cfg={}, now=_NOW, live=True)
        assert tally["considered"] == 0, tally
        statuses = current_statuses(tmp_path)
        assert all(statuses[i] == "queued" for i in ids)

    def test_the_account_filter_scopes_the_sweep(self, tmp_path):
        from engine.marketing import approval_desk as desk

        mine = _seed(tmp_path, account="flagship")
        theirs = _seed(tmp_path, account="sophia",
                       text="$SLB reclaimed 52.4 and held it. Entry 52.4, "
                            "out below 47.1.",
                       source={"ticker": "SLB", "entry": 52.4,
                               "invalidation": 47.1,
                               "media_url": "https://r2.example/s.png"})
        tally = desk.run(tmp_path, cfg={}, now=_NOW, live=True, account="flagship")
        assert tally["approved_ids"] == [mine]
        assert theirs not in tally["approved_ids"]

    def test_an_audit_that_raises_holds_rather_than_approves(self, tmp_path, monkeypatch):
        """A check that crashed proved nothing. The conservative verdict is the
        only safe one — the item stays queued for a human."""
        from engine.marketing import approval_desk as desk
        from engine.marketing.outbox import current_statuses

        iid = _seed(tmp_path)

        def _boom(*a, **kw):
            raise RuntimeError("gate exploded")

        monkeypatch.setattr(desk, "audit_item", _boom)
        tally = desk.run(tmp_path, cfg={}, now=_NOW, live=True)
        assert tally["held"] == 1 and tally["approved"] == 0, tally
        assert current_statuses(tmp_path)[iid] == "queued"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Publisher integration — approved AND dispatched in ONE sweep
# ─────────────────────────────────────────────────────────────────────────────

class _FakePublisher:
    """Stand-in backend that records calls and never touches the network."""

    backend = "buffer"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, **kwargs):
        from engine.marketing.social_publisher import Receipt
        self.calls.append(kwargs)
        at_iso = (kwargs.get("now") or _NOW).strftime("%Y-%m-%dT%H:%M:%SZ")
        return Receipt(True, "buf-post-1", None, None, self.backend, at_iso)

    def list_channels(self):
        return [{"id": "buf-chan-123", "service": "twitter", "name": "Flagship"}]


def _write_cfg(tmp_path: Path, *, desk_enabled: bool = True) -> None:
    """A publisher config with the desk armed and the legacy auto-approve lane
    in its PRODUCTION shape (`auto_approve_scope: kinds`), which is exactly the
    configuration under which planned kinds had no path to live."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "marketing.yml").write_text(
        "sentinel:\n"
        "  max_posts_per_account_per_day: 20\n"
        "publish:\n"
        "  backend: buffer\n"
        "  require_approval: true\n"
        "  auto_approve: true\n"
        "  auto_approve_scope: kinds\n"
        "  auto_approve_kinds: [mover, theme_list]\n"
        "  min_minutes_between_any_posts: 0\n"
        "  media_enabled: false\n"
        "  channels:\n"
        "    flagship: \"buf-chan-123\"\n"
        "  links_allowed:\n"
        "    flagship: false\n"
        "approval_desk:\n"
        f"  enabled: {'true' if desk_enabled else 'false'}\n"
        "  max_approvals_per_sweep: 40\n",
        encoding="utf-8",
    )


def _write_fresh_quotes(tmp_path: Path, tickers: tuple[str, ...]) -> None:
    """A live-quotes snapshot so the publisher's tape gate can verify the
    fixture tickers (a signal it cannot verify is HELD at dispatch, by design)."""
    import json as _json
    p = tmp_path / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    ts_ms = int(_NOW.timestamp() * 1000)
    (p / "live_quotes_snapshot.json").write_text(_json.dumps({
        "asof": _NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quotes": {t: {"price": 190.0, "prevClose": 189.0, "changePct": 0.5,
                       "ts": ts_ms} for t in tickers},
    }), encoding="utf-8")


class TestPublisherIntegration:

    def test_a_planned_item_is_approved_and_dispatched_in_the_same_sweep(
            self, tmp_path, monkeypatch):
        """THE DEFECT, CLOSED END TO END.

        Under the production config (`auto_approve_scope: kinds`) a planned
        `signal` is invisible to the auto-approve pass and the decisions path is
        empty, so before the desk this item could only sit queued until a reaper
        took it. Here it goes queued → approved → POSTED inside one sweep.

        PINS the dispatch, not just the transition: `fake.calls` is what proves
        the desk's approval actually reaches the network path, and the ledger
        actor proves it was the desk that cleared it rather than the legacy pass.
        """
        import scripts.marketing_publisher as pub
        from engine.marketing.outbox import current_statuses, read_ledger

        _write_cfg(tmp_path)
        _write_fresh_quotes(tmp_path, ("PLTR",))
        iid = _seed(tmp_path)

        fake = _FakePublisher()
        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
        monkeypatch.setenv("BUFFER_TOKEN", "test-token")
        monkeypatch.setattr(pub, "_make_publisher",
                            lambda backend, *, token, cfg: fake)
        rc = pub.main(["--live", "--root", str(tmp_path),
                       "--now", "2026-07-31T16:00:00Z"])

        assert rc == 0
        assert current_statuses(tmp_path)[iid] == "posted", read_ledger(tmp_path)
        assert len(fake.calls) == 1, fake.calls
        approve_row = [r for r in read_ledger(tmp_path)
                       if r["id"] == iid and r["to"] == "approved"][0]
        assert approve_row["actor"] == "approval-desk", approve_row

    def test_the_same_sweep_leaves_the_breaking_and_mover_lanes_untouched(
            self, tmp_path, monkeypatch):
        """The desk is additive. `breaking` keeps its own immediate path and
        `mover` keeps kind-scoped auto-approve — neither may acquire an
        `approval-desk` ledger row, and the mover must still post.
        """
        import scripts.marketing_publisher as pub
        from engine.marketing.outbox import current_statuses, read_ledger

        _write_cfg(tmp_path)
        _write_fresh_quotes(tmp_path, ("PLTR", "NVDA"))
        planned = _seed(tmp_path)
        breaking = _seed(
            tmp_path, kind="breaking", provenance="press_lane",
            source={"lane": "press"},
            text="Fed holds rates steady at 4.25%, third meeting running.")
        mover = _seed(
            tmp_path, kind="mover", provenance="publisher_live_movers",
            source={"ticker": "NVDA", "baseline_pct": 0.5},
            text="$NVDA up 0.5% on the session, quietly leading the tape.")

        fake = _FakePublisher()
        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
        monkeypatch.setenv("BUFFER_TOKEN", "test-token")
        monkeypatch.setattr(pub, "_make_publisher",
                            lambda backend, *, token, cfg: fake)
        pub.main(["--live", "--root", str(tmp_path),
                  "--now", "2026-07-31T16:00:00Z"])

        ledger = read_ledger(tmp_path)
        desk_rows = {r["id"] for r in ledger if r.get("actor") == "approval-desk"}
        assert desk_rows == {planned}, desk_rows
        # The breaking item never entered the desk's scope and is still queued
        # for its own lane; the mover was cleared by the legacy scoped pass.
        statuses = current_statuses(tmp_path)
        assert statuses[breaking] == "queued", statuses[breaking]
        mover_rows = [r for r in ledger if r["id"] == mover and r["to"] == "approved"]
        assert mover_rows and mover_rows[0]["actor"] == "publisher-autoapprove"

    def test_the_config_kill_switch_reaches_the_publisher(self, tmp_path, monkeypatch):
        """`approval_desk.enabled: false` in the real config file → the planned
        item stays queued through a full live sweep and nothing posts."""
        import scripts.marketing_publisher as pub
        from engine.marketing.outbox import current_statuses

        _write_cfg(tmp_path, desk_enabled=False)
        _write_fresh_quotes(tmp_path, ("PLTR",))
        iid = _seed(tmp_path)

        fake = _FakePublisher()
        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
        monkeypatch.setenv("BUFFER_TOKEN", "test-token")
        monkeypatch.setattr(pub, "_make_publisher",
                            lambda backend, *, token, cfg: fake)
        pub.main(["--live", "--root", str(tmp_path),
                  "--now", "2026-07-31T16:00:00Z"])

        assert current_statuses(tmp_path)[iid] == "queued"
        assert fake.calls == []

    def test_the_desk_counters_reach_the_activity_row(self, tmp_path, monkeypatch):
        """The Floor's loss ledger reads the activity row and nothing else. A
        counter that never lands there is a gate the operator cannot see."""
        import scripts.marketing_publisher as pub
        from engine.marketing.outbox import read_activity

        _write_cfg(tmp_path)
        _write_fresh_quotes(tmp_path, ("PLTR",))
        _seed(tmp_path)
        _seed(tmp_path, kind="education", source={},
              text="Macro without the jargon.")

        fake = _FakePublisher()
        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
        monkeypatch.setenv("BUFFER_TOKEN", "test-token")
        monkeypatch.setattr(pub, "_make_publisher",
                            lambda backend, *, token, cfg: fake)
        pub.main(["--live", "--root", str(tmp_path),
                  "--now", "2026-07-31T16:00:00Z"])

        row = read_activity(tmp_path, n=1)[-1]
        assert row["desk_approved"] == 1, row
        assert row["desk_quarantined"] == 1, row
        assert row["desk_disabled"] == 0, row
        for key in ("desk_held", "desk_capped", "desk_expired"):
            assert key in row, key

    def test_a_disabled_desk_is_visible_as_a_counter_not_a_silence(
            self, tmp_path, monkeypatch):
        """`desk_disabled` is a 0/1 COUNTER because the Floor's loss ledger
        renders numbers and silently skips strings. A status string here would
        make "the operator switched the desk off" look exactly like "the desk
        ran and cleared nothing"."""
        import scripts.marketing_publisher as pub
        from engine.marketing.outbox import read_activity

        _write_cfg(tmp_path, desk_enabled=False)
        _write_fresh_quotes(tmp_path, ("PLTR",))
        _seed(tmp_path)

        fake = _FakePublisher()
        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
        monkeypatch.setenv("BUFFER_TOKEN", "test-token")
        monkeypatch.setattr(pub, "_make_publisher",
                            lambda backend, *, token, cfg: fake)
        pub.main(["--live", "--root", str(tmp_path),
                  "--now", "2026-07-31T16:00:00Z"])

        row = read_activity(tmp_path, n=1)[-1]
        assert row["desk_disabled"] == 1, row
        assert isinstance(row["desk_disabled"], int)


# ─────────────────────────────────────────────────────────────────────────────
# 4. The Floor — plain words for every desk counter
# ─────────────────────────────────────────────────────────────────────────────

class TestFloorWords:

    def test_every_desk_counter_has_plain_words(self):
        """The general guard (`test_admin_marketing_floor.py`) already walks the
        publisher's activity row; this one names the desk's counters explicitly
        so a rename cannot quietly drop one back to a raw slug."""
        from admin.marketing_floor import _ACTIVITY_WORDS

        for key in ("desk_approved", "desk_quarantined", "desk_held",
                    "desk_capped", "desk_expired", "desk_disabled"):
            words = _ACTIVITY_WORDS[key]
            assert words and words == words.lower()
            for banned in ("approval_desk", "jaccard", "invented_level",
                           "unverifiable", "transition", "ttl", "regex",
                           "provenance"):
                assert banned not in words.lower(), (key, words)

    def test_held_reads_as_work_left_for_the_operator_not_as_a_rejection(self):
        """The word choice IS the feature. `held` means the desk had nothing to
        check the numbers against — that queue is the operator's, and calling it
        "rejected" would hide the only work left for a human."""
        from admin.marketing_floor import _ACTIVITY_WORDS

        words = _ACTIVITY_WORDS["desk_held"].lower()
        assert "you" in words or "human" in words, words
        for wrong in ("rejected", "failed", "bad"):
            assert wrong not in words, words

    def test_the_desk_losses_land_in_the_loss_half(self):
        """A post the desk pulled, held or capped did not go out. Counting it as
        anything but a loss is the tinted-window defect in miniature."""
        from admin.marketing_floor import _LOSS_COUNTERS

        for key in ("desk_quarantined", "desk_held", "desk_capped",
                    "desk_expired"):
            assert key in _LOSS_COUNTERS, key
        # Work done, not work lost.
        assert "desk_approved" not in _LOSS_COUNTERS
        assert "desk_disabled" not in _LOSS_COUNTERS

    def test_the_loss_ledger_renders_the_desk_counters(self):
        from admin.marketing_floor import _activity_ledger

        blk = _activity_ledger({"at": "2026-07-31T16:00:00Z", "lane": "publisher_live",
                            "posted": 3, "desk_approved": 4,
                            "desk_quarantined": 2, "desk_held": 5,
                            "desk_capped": 1, "desk_expired": 0,
                            "desk_disabled": 0})
        by_key = {ln["key"]: ln for ln in blk["lines"]}
        assert by_key["desk_held"]["mapped"] is True
        assert by_key["desk_held"]["is_loss"] is True
        assert by_key["desk_approved"]["is_loss"] is False
        assert blk["lost_total"] == 8
