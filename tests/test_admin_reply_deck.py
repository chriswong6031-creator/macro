"""tests/test_admin_reply_deck.py — the operator's reply deck (admin payload + writes).

Three things are pinned here, and each of them is a defect that shipped or
nearly shipped in this lane:

  1. THE DARK DIAGNOSIS. Five independent keys arm the reply desk and four of
     them fail SILENTLY — an empty author register polls cleanly and produces
     nothing, which reads as "quiet desk", not "dark desk". The deck must name
     which key is off, from the tree the key actually lives in.

  2. THE EDIT IS A SUPERSESSION AND THE CRITICS RUN AGAIN. The operator is a
     second writer, and the queue is a bypass around every generation law
     unless the gate is in front of him too. The self-exclusion from the
     near-dup corpus is load-bearing and is pinned against the version of the
     call that omits it.

  3. OPENING A PANEL MUST NOT MOVE AN ITEM. The one dangerous half of reading
     this store is the lease release; releasing a lease whose receipt is still
     pending drops the item to `queued`, which has no edge to `sent`, so a
     reply that is already PUBLIC goes permanently uncounted.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from _xgw6_helpers import DRAFT, NOW, PARENT, make_reply_item  # noqa: E402
from admin import marketing as M  # noqa: E402
from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_export as rx  # noqa: E402
from engine.marketing import reply_queue as rq  # noqa: E402

#: A clean rewrite of DRAFT that keeps every figure the machine already cleared.
#: It also carries a human-register marker, because the critic roster this suite
#: screens against is the LIVE one and it now includes `warmth_register` — an
#: edit fixture that is a pure instrument readout is refused, correctly.
GOOD_EDIT = ("Fair point, and the thing that argues against it: IG spreads "
             "widened 12.5% while capex guidance held.")


def _seed(store: Path, *, account: str = "kelly", now: datetime = NOW,
          draft: str = DRAFT, thread: str = "1900000000000000001") -> dict:
    item = make_reply_item(account=account, now=now, draft=draft, thread=thread)
    item["family"] = "missing_variable"
    item["score_features"] = {
        "author_tier": 0.8, "age_fit": 0.92,
        "_context": {"tier": "conversion", "age_min": 8.4, "reply_count": 3,
                     "engagement": 41, "relationship_source": "absent"},
    }
    item["score_components"] = {"author_tier": 0.208, "age_fit": 0.202,
                                "velocity": 0.05, "saturation": 0.13}
    out = rq.enqueue(item, store, cfg={})
    assert out["ok"], out
    return item


def _card(deck: dict, account: str, zone: str = "awaiting") -> dict:
    block = [a for a in deck["accounts"] if a["id"] == account]
    assert block, f"{account} missing from the deck payload"
    rows = block[0][zone]
    assert rows, f"{account}.{zone} is empty"
    return rows[0]


# ---------------------------------------------------------------------------
# 1. The dark diagnosis
# ---------------------------------------------------------------------------
def test_empty_deck_reports_only_known_dark_codes_each_with_a_fix(tmp_path):
    """An empty deck must say WHY, not imply nothing was worth replying to.

    Structural against the LIVE config, because which keys are on is an
    operator decision that changes under this test. The codes themselves are
    asserted against synthetic config below, where the rule can be stated.
    """
    deck = M.reply_deck(store=tmp_path, now=NOW)
    assert deck["ok"] is True
    assert deck["totals"]["awaiting"] == 0
    codes = [row["code"] for row in deck["dark"]]
    assert set(codes) <= set(M._RQ_DARK_CODES), f"unknown dark code in {codes}"
    for row in deck["dark"]:
        assert row["title"] and row["detail"], row
        assert row.get("fix"), f"{row['code']} named no file to fix"


def test_dark_reasons_name_every_key_that_is_off():
    """The three the brief names by hand, plus the two silent ones."""
    off = M._reply_dark_reasons(
        {"reply_desk": {"enabled": False, "producer": {"enabled": False}}},
        {"invoked": False, "lanes": ["press"], "units": ["press.service"]},
        {"ok": True, "errors": [], "enabled_total": 0, "listed_total": 21},
        {"kelly": "M0", "cici": "M0"})
    codes = [r["code"] for r in off]
    assert codes == ["desk_disabled", "lane_not_invoked", "producer_off",
                     "no_targets_enabled", "all_m0"], codes
    assert set(codes) <= set(M._RQ_DARK_CODES)


def test_lane_diagnosis_reads_the_deployed_unit_not_a_constant(tmp_path):
    """`--lane press` is dark for replies; `--lane all` is not.

    Pinned on a synthetic deploy tree rather than on the repo's own, so the
    test states the RULE and does not go stale the day the real unit is fixed.
    """
    deploy = tmp_path / "app" / "deploy"
    deploy.mkdir(parents=True)
    (deploy / "marketing-press-feeds.service").write_text(
        "[Service]\nExecStart=/usr/bin/python -m scripts.marketing_fastlane_daemon "
        "--lane press --interval 75\n", encoding="utf-8")
    press_only = M._reply_lane_invoked(tmp_path)
    assert press_only["invoked"] is False
    assert press_only["lanes"] == ["press"]
    assert "marketing-press-feeds.service" in press_only["units"]

    (deploy / "marketing-reply.service").write_text(
        "[Service]\nExecStart=/usr/bin/python -m scripts.marketing_fastlane_daemon "
        "--lane all --interval 120\n", encoding="utf-8")
    both = M._reply_lane_invoked(tmp_path)
    assert both["invoked"] is True
    assert set(both["lanes"]) == {"press", "all"}


def test_lane_diagnosis_is_none_when_no_daemon_unit_exists(tmp_path):
    """No unit file is 'unknown', never a confident 'wired'."""
    assert M._reply_lane_invoked(tmp_path)["invoked"] is None


def test_dark_list_is_empty_when_every_key_is_armed(tmp_path):
    cfg = {"reply_desk": {"enabled": True, "producer": {"enabled": True}}}
    lane = {"invoked": True, "lanes": ["all"], "units": ["x.service"]}
    register = {"ok": True, "errors": [], "enabled_total": 4, "listed_total": 6}
    assert M._reply_dark_reasons(cfg, lane, register, {"kelly": "M1"}) == []


def test_one_desk_off_m0_clears_the_all_m0_diagnosis():
    cfg = {"reply_desk": {"enabled": True, "producer": {"enabled": True}}}
    lane = {"invoked": True, "lanes": ["all"], "units": []}
    register = {"ok": True, "errors": [], "enabled_total": 4, "listed_total": 6}
    rows = M._reply_dark_reasons(cfg, lane, register, {"kelly": "M1", "cici": "M0"})
    assert [r["code"] for r in rows] == []


# ---------------------------------------------------------------------------
# 2. The burst header
# ---------------------------------------------------------------------------
def test_burst_reads_the_persona_territory_clock(tmp_path):
    """Cici's Asia windows come from her committed spec, not from this panel."""
    deck = M.reply_deck(store=tmp_path, now=NOW)
    cici = [r for r in deck["burst"]["accounts"] if r["id"] == "cici"]
    assert cici, "cici is not on the deck"
    row = cici[0]
    assert row["has_session"] is True
    assert row["tz"] == "Asia/Hong_Kong"
    assert row["windows"], "her session windows did not resolve"


def test_burst_liveness_follows_the_clock(tmp_path):
    """A burst is live only inside the desk's own window, in the desk's own tz."""
    # 03:00 UTC = 11:00 HK — inside cici's 08:00-17:00 cash-session window.
    inside = datetime(2026, 7, 28, 3, 0, tzinfo=timezone.utc)
    # 10:00 UTC = 18:00 HK — between her two windows.
    outside = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)
    live = M.reply_deck(store=tmp_path, now=inside)["burst"]
    dark = M.reply_deck(store=tmp_path, now=outside)["burst"]
    assert "cici" in live["live"]
    assert "cici" not in dark["live"]


def test_burst_counts_waiting_and_headroom_separately(tmp_path):
    """Two numbers, because they bind independently."""
    _seed(tmp_path)
    row = [r for r in M.reply_deck(store=tmp_path, now=NOW)["burst"]["accounts"]
           if r["id"] == "kelly"][0]
    assert row["waiting"] == 1
    # Headroom is cap minus sends, never negative — and at M0 the cap is a
    # code-level 0 that no config value can raise.
    assert row["headroom"] == max(0, int(row["cap"]) - int(row["sent_today"]))
    if row["mode"] == "M0":
        assert row["cap"] == 0


# ---------------------------------------------------------------------------
# 3. The card: parent + why
# ---------------------------------------------------------------------------
def test_card_carries_the_parent_and_the_scorer_reasons(tmp_path):
    _seed(tmp_path)
    card = _card(M.reply_deck(store=tmp_path, now=NOW), "kelly")
    assert card["parent_excerpt"] == PARENT
    assert card["parent_author"] == "somequant"
    assert card["parent_age_min"] == 8.4
    assert card["parent_replies"] == 3
    assert card["author_tier"] == "conversion"

    why = {r["key"]: r for r in card["why_target"]}
    assert why["author_tier"]["label"] == "who they are"
    assert why["age_fit"]["means"], "a feature shipped with no plain-word meaning"
    # Ranked by how much each reason actually carried the pick.
    contribs = [abs(r["contribution"]) for r in card["why_target"]]
    assert contribs == sorted(contribs, reverse=True)


def test_why_draft_names_the_missing_gift_instead_of_inventing_one(tmp_path):
    """`make_item` has no field for `components.gift`, so it is dropped.

    The deck must SAY so. Substituting the draft's first line would read as the
    gift and frequently not be it.
    """
    _seed(tmp_path)
    why = _card(M.reply_deck(store=tmp_path, now=NOW), "kelly")["why_draft"]
    assert why["gift"] is None
    assert any("components.gift" in m for m in why["missing"])
    # What IS knowable comes from the committed family register.
    assert why["family"]["id"] == "missing_variable"
    assert why["family"]["move"], "the family's reasoning move did not resolve"
    assert why["family"]["trigger"], "the family's response trigger did not resolve"
    assert "12.5%" in why["numbers"]


def test_why_draft_uses_a_persisted_gift_when_a_lane_stores_one(tmp_path):
    item = _seed(tmp_path)
    del item  # the stored row is what matters
    state = rq.fold_state(tmp_path)
    iid = next(iter(state["items"]))
    families = {"missing_variable": {"label": "missing variable", "move": "m", "trigger": "t"}}
    stored = dict(state["items"][iid], components={"gift": "Equal weight closed flat."})
    why = M._reply_why_draft(stored, families, {})
    assert why["gift"] == "Equal weight closed flat."
    assert not [m for m in why["missing"] if "gift" in m]


# ---------------------------------------------------------------------------
# 4. Export state — "approved" is four different things
# ---------------------------------------------------------------------------
def test_m0_approval_is_parked_not_exported():
    """Approval at M0 is a park, by design — and the rail's `approved` status
    cannot say so on its own."""
    out = M._reply_export_state("rq-x", status="approved", mode="M0",
                                state={"claims": {}, "last": {}},
                                exported=set(), pending=set())
    assert out["stage"] == "parked"
    assert "M0" in out["label"]


def test_export_stage_distinguishes_mirrored_from_awaiting_export(tmp_path):
    item = _seed(tmp_path)
    rq.approve(item["id"], root=tmp_path)
    state = {"claims": {}, "last": {}}
    ids = {item["id"]}
    awaiting = M._reply_export_state(item["id"], status="approved", mode="M1",
                                     state=state, exported=set(), pending=set())
    mirrored = M._reply_export_state(item["id"], status="approved", mode="M1",
                                     state=state, exported=ids, pending=set())
    assert awaiting["stage"] == "awaiting_export"
    assert mirrored["stage"] == "exported"


def test_export_stage_reports_a_pending_receipt_and_a_confirmed_send():
    iid = "rq-x"
    pending = M._reply_export_state(iid, status="claimed", mode="M1",
                                    state={"claims": {}, "last": {}},
                                    exported={iid}, pending={iid})
    assert pending["stage"] == "receipt_pending"

    sent = M._reply_export_state(
        iid, status="sent", mode="M1",
        state={"claims": {}, "last": {iid: {"receipt": {
            "url": "https://x.com/kelly/status/9", "screenshot": "/tmp/a.png",
            "holder": "desk-1"}}}},
        exported=set(), pending=set())
    assert sent["stage"] == "sent"
    assert sent["url"].endswith("/9")
    assert sent["holder"] == "desk-1"


# ---------------------------------------------------------------------------
# 5. Opening the deck must not move an item
# ---------------------------------------------------------------------------
def test_opening_the_deck_does_not_release_a_lease_with_a_pending_receipt(tmp_path):
    """The one dangerous half of reading this store.

    A released lease drops the item to `queued`, which has no edge to `sent` —
    so an already-PUBLIC reply would go permanently uncounted while the cap
    handed its slot back.
    """
    item = _seed(tmp_path)
    rq.approve(item["id"], root=tmp_path)
    assert rq.claim(item["id"], holder="desk-1", lease_s=1, root=tmp_path, now=NOW)
    receipts = rx.receipts_dir(tmp_path)
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / f"{item['id']}.json").write_text(
        json.dumps({"id": item["id"], "url": "https://x.com/kelly/status/9"}),
        encoding="utf-8")

    later = NOW + timedelta(minutes=5)
    released, _killed, state = M._reply_desk_open(tmp_path, ts=later)
    assert item["id"] not in (released or [])
    assert state["status"][item["id"]] == "claimed"


def test_opening_the_deck_does_release_a_dead_lease_with_no_receipt(tmp_path):
    """The inverse: a session that simply died must hand the item back."""
    item = _seed(tmp_path)
    rq.approve(item["id"], root=tmp_path)
    assert rq.claim(item["id"], holder="desk-1", lease_s=1, root=tmp_path, now=NOW)
    released, _killed, state = M._reply_desk_open(tmp_path, ts=NOW + timedelta(minutes=5))
    assert item["id"] in (released or [])
    assert state["status"][item["id"]] != "claimed"


# ---------------------------------------------------------------------------
# 6. Edit — validation
# ---------------------------------------------------------------------------
def test_validate_returns_the_critic_reason_verbatim(tmp_path):
    """A figure the machine never vetted is a figure nobody vetted."""
    item = _seed(tmp_path)
    bad = "IG spreads widened 44.7% this week while capex guidance held. Credit is the test."
    res = M.validate_reply_text(item["id"], bad, store=tmp_path, now=NOW)
    assert res["ok"] is True
    assert res["clean"] is False
    assert "fact_discipline" in res["rejected_by"]
    # VERBATIM. Not paraphrased, not mapped to a friendlier label: the
    # vocabulary the sheet teaches must be the vocabulary the pipeline uses.
    assert "fact_discipline: number '44.7%' not in whitelist" in res["violations"]
    # ...and every critic that rejected is represented in the reason list, so a
    # roster change cannot silently drop an objection off the sheet.
    for name in res["rejected_by"]:
        assert any(v.startswith(f"{name}:") for v in res["violations"]), name


def test_validate_allows_a_figure_the_original_draft_already_carried(tmp_path):
    """The whitelist is the ORIGINAL DRAFT's tokens — strictly tighter than the
    own-feed whitelist that cleared it, because make_item does not persist it."""
    item = _seed(tmp_path)
    res = M.validate_reply_text(item["id"], GOOD_EDIT, store=tmp_path, now=NOW)
    assert res["clean"] is True, res["violations"]
    assert res["editable"] is True


def test_validate_refuses_an_unchanged_draft(tmp_path):
    item = _seed(tmp_path)
    res = M.validate_reply_text(item["id"], DRAFT, store=tmp_path, now=NOW)
    assert res["unchanged"] is True
    assert res["clean"] is False


def test_validate_writes_nothing(tmp_path):
    item = _seed(tmp_path)
    before = rq.fold_state(tmp_path)["status"][item["id"]]
    M.validate_reply_text(item["id"], GOOD_EDIT, store=tmp_path, now=NOW)
    M.validate_reply_text(item["id"], "spreads widened 44.7%", store=tmp_path, now=NOW)
    after = rq.fold_state(tmp_path)
    assert after["status"][item["id"]] == before
    assert len(after["items"]) == 1


def test_the_edited_draft_is_excluded_from_its_own_near_dup_corpus(tmp_path):
    """LOAD-BEARING, and pinned against the call that omits it.

    The draft being rewritten is by construction the nearest neighbour of its
    own rewrite. Leaving it in the corpus rejects every small edit as a repeat
    of itself, which would make the edit button useless for exactly the case it
    exists for.
    """
    seeded = ("Fair point, and the thing that argues against it: IG spreads "
              "widened 12.5% while capex guidance held.")
    one_word = seeded.replace("argues against", "cuts against")
    item = _seed(tmp_path, draft=seeded)
    res = M.validate_reply_text(item["id"], one_word, store=tmp_path, now=NOW)
    assert res["clean"] is True, res["violations"]

    # The same text, screened with the item left in the corpus, is refused —
    # so the exclusion is doing the work, not the threshold being lenient.
    with_self = rc.run_critics(one_word, {
        "account": "kelly", "family": "missing_variable",
        "numbers_whitelist": rc.number_tokens(seeded),
        "corpus": [{"draft": seeded, "account": "kelly"}]})
    assert with_self["rejected_by"] == ["corpus_near_dup"]


# ---------------------------------------------------------------------------
# 7. Edit — the write
# ---------------------------------------------------------------------------
def test_edit_supersedes_and_approves(tmp_path):
    item = _seed(tmp_path)
    res = M.edit_reply(item["id"], GOOD_EDIT, store=tmp_path, now=NOW)
    assert res["ok"] is True, res
    assert res["superseded"] == item["id"]
    assert res["approved"] is True

    state = rq.fold_state(tmp_path)
    assert state["status"][item["id"]] == "rejected"
    assert state["status"][res["id"]] == "approved"
    new = state["items"][res["id"]]
    assert new["draft"] == GOOD_EDIT
    assert new["provenance"] == "operator_edit"
    assert new["family"] == "missing_variable"
    # The replacement carries a REAL full-roster stamp: the store refuses any
    # other kind, so this asserts the critics genuinely ran on the new text.
    assert rq.validate_critic_stamp(new) == []
    assert set(new["critics"]["critics_run"]) == set(rc.CRITICS)


def test_edit_inherits_the_original_deadline(tmp_path):
    """Editing must not buy a stale reply more time — the window closes on the
    parent post's clock, not on ours."""
    item = _seed(tmp_path)
    res = M.edit_reply(item["id"], GOOD_EDIT, store=tmp_path, now=NOW + timedelta(minutes=20))
    assert res["ok"] is True, res
    assert rq.fold_state(tmp_path)["items"][res["id"]]["expires_at"] == item["expires_at"]


def test_edit_does_not_write_the_taste_corpus(tmp_path):
    """Rejections say what this desk should NOT sound like. "The operator
    improved this one" is the opposite signal."""
    item = _seed(tmp_path)
    assert M.edit_reply(item["id"], GOOD_EDIT, store=tmp_path, now=NOW)["ok"]
    assert rq.read_rejections(tmp_path) == []
    # The ledger still carries the trace, under its own actor.
    rows = [r for r in rq.read_ledger(tmp_path) if r.get("to") == "rejected"]
    assert rows and rows[0]["actor"] == M._RQ_EDIT_ACTOR


def test_edit_refuses_copy_the_critics_reject_and_writes_nothing(tmp_path):
    item = _seed(tmp_path)
    bad = "IG spreads widened 44.7% this week while capex guidance held. Credit is the test."
    res = M.edit_reply(item["id"], bad, store=tmp_path, now=NOW)
    assert res["ok"] is False
    assert "fact_discipline: number '44.7%' not in whitelist" in res["violations"]
    state = rq.fold_state(tmp_path)
    assert state["status"][item["id"]] == "queued"
    assert len(state["items"]) == 1


def test_edit_refuses_an_item_that_is_no_longer_waiting_on_you(tmp_path):
    item = _seed(tmp_path)
    rq.approve(item["id"], root=tmp_path)
    res = M.edit_reply(item["id"], GOOD_EDIT, store=tmp_path, now=NOW)
    assert res["ok"] is False
    assert "approved" in res["error"]
    assert rq.fold_state(tmp_path)["status"][item["id"]] == "approved"


def test_edit_refuses_an_unchanged_or_empty_draft(tmp_path):
    item = _seed(tmp_path)
    assert M.edit_reply(item["id"], DRAFT, store=tmp_path, now=NOW)["ok"] is False
    assert M.edit_reply(item["id"], "   ", store=tmp_path, now=NOW)["ok"] is False
    assert rq.fold_state(tmp_path)["status"][item["id"]] == "queued"


def test_edit_refuses_copy_over_the_reply_char_cap(tmp_path):
    item = _seed(tmp_path)
    cap = M._rq_char_cap()
    res = M.edit_reply(item["id"], "spreads held. " * 60, store=tmp_path, now=NOW)
    assert res["ok"] is False
    assert str(cap) in res["error"]
    assert rq.fold_state(tmp_path)["status"][item["id"]] == "queued"


def test_char_cap_comes_from_the_gate_that_enforces_it():
    from engine.marketing import reply_voice as rv
    assert M._rq_char_cap() == rv.MAX_REPLY_CHARS


def test_edit_refuses_when_another_live_item_owns_the_conversation(tmp_path):
    """Checked BEFORE the original is killed: `enqueue`'s one-owner lock would
    otherwise refuse the replacement after the kill, leaving the operator with
    a fixed typo and no reply at all."""
    first = _seed(tmp_path)
    # A second desk on the same thread — the lock the enqueue would trip on.
    sibling = make_reply_item(account="cici", now=NOW,
                              draft="Overnight the same spread move showed up in HK credit.")
    sibling["thread_key"] = first["thread_key"]
    sibling["id"] = sibling["id"] + "-sib"
    rq.append_jsonl(rq._items_path(tmp_path), sibling)

    res = M.edit_reply(first["id"], GOOD_EDIT, store=tmp_path, now=NOW)
    assert res["ok"] is False
    assert "one conversation, one owner" in res["error"]
    assert rq.fold_state(tmp_path)["status"][first["id"]] == "queued"


def test_edit_of_an_unknown_item_is_refused(tmp_path):
    assert M.edit_reply("rq-nope", GOOD_EDIT, store=tmp_path, now=NOW)["ok"] is False
    assert M.validate_reply_text("rq-nope", GOOD_EDIT, store=tmp_path,
                                 now=NOW)["ok"] is False


# ---------------------------------------------------------------------------
# 8. Deck shape
# ---------------------------------------------------------------------------
def test_deck_lists_every_eligible_desk_even_with_nothing_queued(tmp_path):
    """A desk with nothing queued is the case this page exists for; it cannot
    be diagnosed if it is simply absent from the payload."""
    ids = {a["id"] for a in M.reply_deck(store=tmp_path, now=NOW)["accounts"]}
    assert {"kelly", "cici", "sophia", "meagan", "flagship", "founder"} <= ids
    # ...and NOT every account in the fleet: the reply desk is six desks.
    assert "theme_desk" not in ids


def test_deck_ranks_awaiting_by_score_and_breaks_ties_stably(tmp_path):
    _seed(tmp_path, thread="1900000000000000001",
          draft="Equal weight closed flat while the index added 12.5%.")
    hi = make_reply_item(account="kelly", now=NOW, thread="1900000000000000002",
                         draft="Semis carried the tape; breadth did not follow.")
    hi["score"] = 0.95
    rq.enqueue(hi, tmp_path, cfg={})
    rows = [a for a in M.reply_deck(store=tmp_path, now=NOW)["accounts"]
            if a["id"] == "kelly"][0]["awaiting"]
    assert [r["score"] for r in rows] == sorted([r["score"] for r in rows], reverse=True)


def test_deck_reports_a_full_critic_roster_on_every_card(tmp_path):
    """The runbook's claim to the operator — "nine critics cleared this" — is
    true only because the STORE refuses an item without a full-roster passing
    stamp. The card prints the count, so a roster change is visible here."""
    _seed(tmp_path)
    card = _card(M.reply_deck(store=tmp_path, now=NOW), "kelly")
    assert card["critics"]["verdict"] == "pass"
    assert set(card["critics"]["ran"]) == set(rc.CRITICS)


def test_deck_survives_an_unreadable_store(tmp_path):
    bad = tmp_path / "store"
    bad.mkdir()
    (bad / "store").write_text("not a directory", encoding="utf-8")
    deck = M.reply_deck(store=bad, now=NOW)
    # Fail-soft: a dark panel beats a 500. The write paths are the ones that
    # must refuse instead (see the edit tests above).
    assert "ok" in deck


@pytest.mark.parametrize("stage_status,expected", [
    ("queued", "queued"),
    ("rejected", "rejected"),
    ("expired", "expired"),
])
def test_terminal_stages_read_in_operator_words(stage_status, expected):
    out = M._reply_export_state("rq-x", status=stage_status, mode="M0",
                                state={"claims": {}, "last": {}},
                                exported=set(), pending=set())
    assert out["stage"] == expected
    assert out["label"]


def test_an_edited_original_reads_as_replaced_not_skipped(tmp_path):
    """The store has ONE terminal kill, so an edit retires the original through
    the same `rejected` edge a skip uses. Only the ledger actor tells them
    apart, and "you passed on this" is a false sentence about a draft the
    operator improved."""
    item = _seed(tmp_path)
    res = M.edit_reply(item["id"], GOOD_EDIT, store=tmp_path, now=NOW)
    assert res["ok"] is True, res
    history = [a for a in M.reply_deck(store=tmp_path, now=NOW)["accounts"]
               if a["id"] == "kelly"][0]["recent"]
    original = [c for c in history if c["id"] == item["id"]]
    assert original, "the superseded original vanished from the deck"
    assert original[0]["export"]["stage"] == "replaced"

    # ...and a genuine skip still reads as a skip.
    other = _seed(tmp_path, thread="1900000000000000009",
                  draft="Semis carried the tape and breadth did not follow at all.")
    assert M.reject_reply(other["id"], reason="too flat", store=tmp_path)["ok"]
    history = [a for a in M.reply_deck(store=tmp_path, now=NOW)["accounts"]
               if a["id"] == "kelly"][0]["recent"]
    skipped = [c for c in history if c["id"] == other["id"]]
    assert skipped and skipped[0]["export"]["stage"] == "rejected"
