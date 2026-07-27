"""tests/test_marketing_publish_time_read.py — publish-time DAILY READ lane.

Covers engine.marketing.publish_time_content.generate_read_item (the publish-time
generator that builds the "My read on today's move", kind=event, post from the
FRESH daily brief on the after-close ladder slot) and the nightly gate in
engine.marketing.content_studio (event dropped from the plan when
publish.publish_time_read is armed, so the read never double-posts).

The load-bearing test here is DARK DEFAULT: with publish.publish_time_read.enabled
false (or absent) the generator returns a disabled report and writes NO ledger
rows — nothing can auto-post under the default config.

Conventions mirror tests/test_marketing_publish_time_content.py: tmp_path roots,
injected now= for determinism (the after-close slot is a PACIFIC-clock concept,
so `now` is built from a Pacific wall-clock and converted to UTC), ZERO network,
engine modules imported inside the module.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from engine.marketing import outbox, publish_time_content as pt

_PT = ZoneInfo("America/Los_Angeles")


def _pt_utc(y: int, m: int, d: int, hh: int, mm: int = 0) -> datetime:
    """A Pacific wall-clock instant, as an aware UTC datetime (what the publisher
    passes as `now`). S8 = 18:00 PT; a Pacific evening is the NEXT UTC day."""
    return datetime(y, m, d, hh, mm, tzinfo=_PT).astimezone(timezone.utc)


# Thursday 2026-07-23, 18:30 PT → the S8 (after-close) ladder slot.
NOW_S8 = _pt_utc(2026, 7, 23, 18, 30)
# Same day, 10:05 PT → S4 (mid-morning), a WRONG slot for the daily read.
NOW_WRONG = _pt_utc(2026, 7, 23, 10, 5)
# Saturday 2026-07-25, 18:30 PT → weekend (Pacific), must never fire.
NOW_SAT = _pt_utc(2026, 7, 25, 18, 30)
# Friday 2026-07-24, 18:30 PT → S8; its UTC instant is SATURDAY — the Pacific
# weekday gate must still admit it (a UTC weekday check would wrongly reject).
NOW_FRI_S8 = _pt_utc(2026, 7, 24, 18, 30)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

# A why_the_tape_moved.primary.direction that has a plain-English mapping in
# market_facts._DRIVER_PLAIN (so event_facts yields a usable driver read).
_DIRECTION = "ai/semis unwind — tech-led de-rating"
_DRIVER_SUBSTR = "AI and chip trade is unwinding"


def _write_brief(tmp: Path, *, direction: str = _DIRECTION,
                 available: bool = True) -> None:
    """Write a fresh daily_brief.json with a why_the_tape_moved primary driver."""
    p = tmp / "site" / "neuralwebdata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "daily_brief.json").write_text(json.dumps({
        "why_the_tape_moved": {
            "available": available,
            "primary": {"direction": direction, "coherence": "aligned"},
        }
    }), encoding="utf-8")


def _cfg(*, enabled: bool = True, slot: str = "S8",
         accounts: list[dict] | None = None,
         channels: dict | None = None,
         personas: dict | None = None) -> dict:
    accounts = accounts or [{"id": "flagship", "voice": "authoritative desk"}]
    channels = channels if channels is not None else {"flagship": "c1"}
    personas = personas if personas is not None else {
        "flagship": {"name": "The Desk", "voice_notes": "terse. Emoji budget: 0-1"}}
    return {
        "publish": {
            "publish_time_read": {"enabled": enabled, "slot": slot},
            "channels": channels,
        },
        "desk_network": {"accounts": accounts},
        "copywriter": {"personas": personas},
    }


def _gen(tmp: Path, cfg: dict, *, now: datetime = NOW_S8, live: bool = True,
         account_filter=None) -> dict:
    state = outbox.fold_state(tmp)
    return pt.generate_read_item(
        tmp, cfg=cfg, now=now, state=state, live=live,
        account_filter=account_filter)


def _rows(tmp: Path) -> list[dict]:
    """Every item record written to the outbox ledger (empty when nothing wrote)."""
    return outbox.read_items(tmp)


# ─────────────────────────────────────────────────────────────────────────────
# 1. DARK DEFAULT — the load-bearing safety test
# ─────────────────────────────────────────────────────────────────────────────

def test_dark_default_disabled_writes_nothing(tmp_path):
    """enabled=false + live=True → disabled report, ZERO ledger rows.

    This is the invariant that keeps the change dark: nothing may auto-post
    under the default config.
    """
    _write_brief(tmp_path)  # a perfectly good brief is present…
    rep = _gen(tmp_path, _cfg(enabled=False), now=NOW_S8, live=True)
    assert rep["enabled"] is False
    assert rep["generated"] == []
    assert rep["would_generate"] == []
    assert any(d["reason"] == "disabled" for d in rep["dropped"])
    assert _rows(tmp_path) == []          # …and STILL nothing was written


def test_dark_default_absent_block_writes_nothing(tmp_path):
    """A config with NO publish_time_read block at all behaves as disabled."""
    _write_brief(tmp_path)
    cfg = _cfg(enabled=True)
    del cfg["publish"]["publish_time_read"]   # block absent entirely
    rep = _gen(tmp_path, cfg, now=NOW_S8, live=True)
    assert rep["enabled"] is False
    assert rep["generated"] == []
    assert _rows(tmp_path) == []


# ─────────────────────────────────────────────────────────────────────────────
# 2. Armed + correct slot
# ─────────────────────────────────────────────────────────────────────────────

def test_armed_dry_run_fills_would_generate_with_driver(tmp_path):
    """Armed, S8, fresh brief, live=False → would_generate carries the event read
    whose text contains the fresh driver line; NOTHING is written."""
    _write_brief(tmp_path)
    rep = _gen(tmp_path, _cfg(), now=NOW_S8, live=False)
    assert rep["enabled"] is True
    assert rep["slot"] == "S8"
    assert len(rep["would_generate"]) == 1
    wg = rep["would_generate"][0]
    assert wg["kind"] == "event"
    assert wg["account"] == "flagship"
    assert _DRIVER_SUBSTR in wg["text"]
    assert _rows(tmp_path) == []          # dry-run writes nothing


def test_armed_live_enqueues_one_event_per_account(tmp_path):
    """Armed, S8, live=True → one queued `event` item per eligible account with
    provenance publisher_live_movers (the scoped auto-approve lane marker)."""
    _write_brief(tmp_path)
    accounts = [{"id": "flagship", "voice": "authoritative desk"},
                {"id": "desk2", "voice": "specialist"}]
    cfg = _cfg(accounts=accounts,
               channels={"flagship": "c1", "desk2": "c2"},
               personas={
                   "flagship": {"name": "The Desk", "voice_notes": "terse. Emoji budget: 0-1"},
                   "desk2": {"name": "The Specialist", "voice_notes": "spicy. Emoji budget: 1"}})
    rep = _gen(tmp_path, cfg, now=NOW_S8, live=True)
    assert len(rep["generated"]) == 2
    rows = _rows(tmp_path)
    assert len(rows) == 2
    assert {r["account"] for r in rows} == {"flagship", "desk2"}
    for r in rows:
        assert r["kind"] == "event"
        assert r["provenance"] == "publisher_live_movers"
        assert r["slot"] == "LIVE-S8"
        assert _DRIVER_SUBSTR in r["text"]


def test_armed_account_filter_scopes_to_one(tmp_path):
    """account_filter restricts generation to the named account."""
    _write_brief(tmp_path)
    accounts = [{"id": "flagship", "voice": "authoritative desk"},
                {"id": "desk2", "voice": "specialist"}]
    cfg = _cfg(accounts=accounts, channels={"flagship": "c1", "desk2": "c2"},
               personas={"flagship": {"name": "The Desk", "voice_notes": "terse"},
                         "desk2": {"name": "Spec", "voice_notes": "spicy"}})
    rep = _gen(tmp_path, cfg, now=NOW_S8, live=True, account_filter="desk2")
    assert len(rep["generated"]) == 1
    rows = _rows(tmp_path)
    assert [r["account"] for r in rows] == ["desk2"]


def test_armed_once_per_day_second_sweep_writes_nothing(tmp_path):
    """A second sweep in the same S8 block does NOT add a second row for an
    account that already posted the read today (fires once/day)."""
    _write_brief(tmp_path)
    cfg = _cfg()
    rep1 = _gen(tmp_path, cfg, now=NOW_S8, live=True)
    assert len(rep1["generated"]) == 1
    rep2 = _gen(tmp_path, cfg, now=NOW_S8, live=True)
    assert rep2["generated"] == []
    assert len(_rows(tmp_path)) == 1      # still exactly one


def test_friday_after_close_is_admitted(tmp_path):
    """Friday 18:30 PT (S8) is a weekday in the Pacific frame even though its UTC
    instant is Saturday — the read must still generate."""
    _write_brief(tmp_path)
    rep = _gen(tmp_path, _cfg(), now=NOW_FRI_S8, live=True)
    assert rep["slot"] == "S8"
    assert len(rep["generated"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. Wrong slot / weekend / no brief → empty report, nothing written
# ─────────────────────────────────────────────────────────────────────────────

def test_wrong_slot_writes_nothing(tmp_path):
    """A mid-morning sweep (not the configured after-close slot) → empty report."""
    _write_brief(tmp_path)
    rep = _gen(tmp_path, _cfg(), now=NOW_WRONG, live=True)
    assert rep["enabled"] is True
    assert rep["generated"] == []
    assert any(d["reason"] == "wrong_slot" for d in rep["dropped"])
    assert _rows(tmp_path) == []


def test_weekend_writes_nothing(tmp_path):
    """Saturday (Pacific) → empty report, nothing written."""
    _write_brief(tmp_path)
    rep = _gen(tmp_path, _cfg(), now=NOW_SAT, live=True)
    assert rep["generated"] == []
    assert any(d["reason"] == "not_weekday" for d in rep["dropped"])
    assert _rows(tmp_path) == []


def test_no_brief_drops_with_reason(tmp_path):
    """Armed + S8 but NO brief and no regime data → dropped no_brief, nothing
    written (event_facts falls back to macro_facts, which is empty here)."""
    # No brief written, no data/regime — event_facts → empty facts.
    rep = _gen(tmp_path, _cfg(), now=NOW_S8, live=True)
    assert rep["generated"] == []
    assert any(d["reason"] == "no_brief" for d in rep["dropped"])
    assert _rows(tmp_path) == []


def test_no_channel_account_is_ineligible(tmp_path):
    """An account without a publish channel id can never post → no_eligible_accounts."""
    _write_brief(tmp_path)
    cfg = _cfg(channels={})   # no channel for flagship
    rep = _gen(tmp_path, cfg, now=NOW_S8, live=True)
    assert rep["generated"] == []
    assert any(d["reason"] == "no_eligible_accounts" for d in rep["dropped"])
    assert _rows(tmp_path) == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. Nightly gating (content_studio.plan_account drop_types)
# ─────────────────────────────────────────────────────────────────────────────

def test_nightly_gate_armed_allocates_no_event():
    """With the read armed, the nightly plan allocates ZERO event slots (the
    publish-time lane owns that post); other types are unaffected."""
    from engine.marketing import content_studio as cs
    acct = {"id": "flagship", "voice": "authoritative desk", "enabled": True}
    items = cs.plan_account(account=acct, plans=[], n_days=7, per_day=8,
                            seed=0, tilt=None, drop_types={"event"})
    kinds = {it.type for it in items}
    assert "event" not in kinds
    # other core types still present
    assert {"signal", "mover", "theme_list"} <= kinds


def test_nightly_gate_default_allocates_event_and_is_unchanged():
    """Flag OFF (drop_types empty/None) → event is allocated AND the plan is
    byte-identical to the pre-change default (drop_types=None)."""
    from engine.marketing import content_studio as cs
    acct = {"id": "flagship", "voice": "authoritative desk", "enabled": True}
    default = cs.plan_account(account=acct, plans=[], n_days=7, per_day=8,
                              seed=0, tilt=None)                      # old default
    empty = cs.plan_account(account=acct, plans=[], n_days=7, per_day=8,
                            seed=0, tilt=None, drop_types=set())      # new default call
    assert "event" in {it.type for it in default}
    assert [it.as_dict() for it in default] == [it.as_dict() for it in empty]
