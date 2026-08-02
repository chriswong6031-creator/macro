"""Reply-desk pacing — burst discipline, caps, and the two per-target floors.

The operator's rule (2026-08-01): a real desk works in 2-4 bursts a day of
15-25 minutes clustered on session hours, with counts that vary and some bursts
skipped — not an even drip across 24 hours. The daily cap cannot express any of
that, so `reply_queue`'s pacing section does.

What this suite is actually guarding, in order of how badly it would hurt:

  1. **Determinism.** A schedule that cannot be reproduced hours later from a
     different process is a schedule nobody can debug. Every plan is a pure
     function of (seed, account, day).
  2. **Variation.** A deterministic plan that is the SAME every day is a
     metronome with a hash in front of it — worse than random, because it looks
     principled.
  3. **The named cap.** Every hold reports WHICH cap held it. "Nothing
     exported" is an outage report; "kelly is between bursts until 16:22Z" is
     an answer.
  4. **What pacing must never do.** It must never refuse to RECORD a reply that
     is already public (`mark_sent`), and it must never be silently on for a
     caller that did not ask for it.

Stdlib + pyyaml only; no network, no LLM.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_queue as rq  # noqa: E402

DRAFT = ("IG spreads widened 12.5% this week while capex guidance held.\n\n"
         "The price move is the reaction. Credit is the test.")


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


@pytest.fixture()
def m1(cfg: dict) -> dict:
    """kelly at M1 with the SHIPPED pacing block — pacing is the subject here."""
    out = json.loads(json.dumps(cfg))
    out["reply_desk"]["mode"]["accounts"]["kelly"] = "M1"
    return out


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    return tmp_path / "reply_desk"


def _stamp() -> dict:
    return rc.stamp({
        "verdict": "pass", "rejected_by": [],
        "critics": [{"critic": n, "verdict": "pass", "reasons": []} for n in rc.CRITICS],
    })


def _item(*, account="kelly", thread="1900000000000000001", author="somequant",
          draft=DRAFT, now: datetime, tier="relationship", ttl_min=45) -> dict:
    return rq.make_item(
        account=account, target_url=f"https://x.com/{author}/status/{thread}",
        parent_author=author, parent_excerpt="capex vs spreads", draft=draft,
        tier=tier, score=0.8, score_components={"author_tier": 0.26},
        critics=_stamp(), ttl_min=ttl_min, now=now,
    )


def _first_active_day(cfg: dict, account: str = "kelly", start=(2026, 8, 3)) -> tuple[str, dict]:
    """The first day whose plan has at least one live burst, and that plan.

    Derived, never hardcoded: a skipped-burst day is legitimate output, so a
    test that pins a literal date is one dice roll away from being about
    nothing.
    """
    base = datetime(*start, tzinfo=timezone.utc)
    for i in range(30):
        day = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        plan = rq.burst_plan(account, day, cfg=cfg)
        if plan["active_bursts"]:
            return day, plan
    raise AssertionError("no day in 30 has a live burst — the plan generator is broken")


def _live_bursts(plan: dict) -> list[dict]:
    return [b for b in plan["bursts"] if not b["skipped"]]


# ===========================================================================
# GATE 1: the plan is deterministic, and it varies
# ===========================================================================
class TestBurstPlanIsDeterministic:
    def test_same_seed_account_and_day_give_an_identical_plan(self, cfg):
        a = rq.burst_plan("kelly", "2026-08-03", cfg=cfg)
        b = rq.burst_plan("kelly", "2026-08-03", cfg=cfg)
        assert a == b

    def test_the_plan_survives_a_process_boundary(self, cfg):
        """sha256, not `hash()`. PYTHONHASHSEED randomises str hashing per
        process, which would make "same inputs, same plan" true only inside one
        run — exactly the guarantee an auditable schedule does not want."""
        import subprocess

        code = (
            "import json,sys,yaml;sys.path.insert(0,%r);"
            "from engine.marketing import reply_queue as q;"
            "cfg=yaml.safe_load(open(%r));"
            "print(json.dumps(q.burst_plan('kelly','2026-08-03',cfg=cfg)))"
            % (str(ROOT), str(ROOT / "config" / "marketing.yml"))
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, env={"PYTHONHASHSEED": "12345", "PATH": "/usr/bin:/bin"})
        assert out.returncode == 0, out.stderr
        assert json.loads(out.stdout) == rq.burst_plan("kelly", "2026-08-03", cfg=cfg)

    def test_a_different_seed_reshuffles_everything(self, cfg):
        other = json.loads(json.dumps(cfg))
        other["reply_desk"]["pacing"]["seed"] = "reply-desk-v2"
        assert (rq.burst_plan("kelly", "2026-08-03", cfg=other)
                != rq.burst_plan("kelly", "2026-08-03", cfg=cfg))


class TestBurstPlanVaries:
    def test_plans_differ_across_days(self, cfg):
        days = [(datetime(2026, 8, 3, tzinfo=timezone.utc) + timedelta(days=i)).strftime("%Y-%m-%d")
                for i in range(30)]
        shapes = {json.dumps([(b["session"], b["start"][11:16], b["items"]) for b in
                              rq.burst_plan("kelly", d, cfg=cfg)["bursts"]]) for d in days}
        assert len(shapes) >= 25, f"only {len(shapes)} distinct shapes in 30 days — a metronome"

    def test_plans_differ_across_accounts_on_the_same_day(self, cfg):
        shapes = {json.dumps(rq.burst_plan(a, "2026-08-03", cfg=cfg)["bursts"])
                  for a in ("kelly", "sophia", "meagan", "flagship")}
        assert len(shapes) == 4, "two desks drew the same schedule"

    def test_burst_counts_durations_and_items_stay_inside_config(self, cfg):
        p = rq.pacing_for(cfg, "kelly")
        for i in range(60):
            day = (datetime(2026, 8, 3, tzinfo=timezone.utc) + timedelta(days=i)).strftime("%Y-%m-%d")
            plan = rq.burst_plan("kelly", day, cfg=cfg)
            assert p["bursts_per_day"]["min"] <= plan["planned_bursts"] <= p["bursts_per_day"]["max"]
            for b in plan["bursts"]:
                assert p["burst_minutes"]["min"] <= b["minutes"] <= p["burst_minutes"]["max"]
                if not b["skipped"]:
                    assert p["items_per_burst"]["min"] <= b["items"] <= p["items_per_burst"]["max"]

    def test_some_bursts_are_skipped_and_some_days_are_full(self, cfg):
        """A skipped burst is a feature. So is a day where every burst runs."""
        skipped = full = 0
        for i in range(60):
            day = (datetime(2026, 8, 3, tzinfo=timezone.utc) + timedelta(days=i)).strftime("%Y-%m-%d")
            plan = rq.burst_plan("kelly", day, cfg=cfg)
            if plan["active_bursts"] < plan["planned_bursts"]:
                skipped += 1
            else:
                full += 1
        assert skipped > 0, "no burst was ever skipped — this is a cron job"
        assert full > 0, "every day lost a burst — skip_probability is too high"

    def test_the_configured_burst_maximum_is_actually_reachable(self, cfg):
        """One burst per session, so `bursts_per_day.max` above the number of
        declared sessions is silently unreachable and the operator's stated
        2-4 quietly becomes a 2-3. This test caught exactly that: the first
        session map shipped three windows against a max of four."""
        p = rq.pacing_for(cfg, "kelly")
        want = int(p["bursts_per_day"]["max"])
        assert len(p["sessions"]) >= want, (
            f"{len(p['sessions'])} sessions cannot produce {want} bursts")
        seen = {rq.burst_plan("kelly",
                              (datetime(2026, 8, 3, tzinfo=timezone.utc) + timedelta(days=i))
                              .strftime("%Y-%m-%d"), cfg=cfg)["planned_bursts"]
                for i in range(60)}
        assert want in seen, f"planned_bursts never reached {want}; saw {sorted(seen)}"

    def test_the_clamp_is_reported_rather_than_hidden(self, cfg):
        """If a future config DOES ask for more bursts than sessions, the plan
        must say so out loud instead of quietly capping."""
        narrow = json.loads(json.dumps(cfg))
        narrow["reply_desk"]["pacing"]["bursts_per_day"] = {"min": 6, "max": 6}
        plan = rq.burst_plan("kelly", "2026-08-03", cfg=narrow)
        assert plan["bursts_requested"] == 6
        assert plan["planned_bursts"] == plan["session_count"] < 6


# ===========================================================================
# GATE 2: sessions track the exchange clock, not the offset
# ===========================================================================
class TestSessionsAreLocalNotUtc:
    #: A jitter-free harness: ONE session whose window is exactly as long as the
    #: burst, so `room == 0` and the start offset is always 0. Without this the
    #: dice pick a different session and a different offset on every date, and a
    #: cross-date comparison of start times is measuring randomness, not the
    #: timezone conversion — which is how the first version of the DST test
    #: below passed even with the zone forced to UTC.
    @staticmethod
    def _pinned(cfg: dict, tz: str = "America/New_York") -> dict:
        out = json.loads(json.dumps(cfg))
        out["reply_desk"]["pacing"].update({
            "tz": tz,
            "bursts_per_day": {"min": 1, "max": 1},
            "burst_minutes": {"min": 15, "max": 15},
            "skip_probability": 0.0,
            "sessions": {"pre_open": {"start": "08:05", "end": "08:20"}},
            "accounts": {},
        })
        return out

    def test_the_pinned_harness_really_removes_the_jitter(self, cfg):
        """Guard on the guard: if the harness ever regains jitter, the DST test
        below silently goes back to measuring dice."""
        pinned = self._pinned(cfg)
        starts = {rq.burst_plan("kelly", f"2026-08-{d:02d}", cfg=pinned)["bursts"][0]["start"][11:16]
                  for d in range(3, 24)}
        assert len(starts) == 1, f"harness still jitters: {sorted(starts)}"

    def test_windows_shift_with_dst(self, cfg):
        """A UTC-pinned window drifts an hour twice a year against the market it
        tracks: the pre-open burst silently becomes an at-the-open burst every
        spring. The LOCAL start must be identical across the DST boundary and
        the UTC start must not be."""
        from zoneinfo import ZoneInfo

        ny = ZoneInfo("America/New_York")
        pinned = self._pinned(cfg)
        summer = rq.burst_plan("kelly", "2026-08-03", cfg=pinned)["bursts"][0]
        winter = rq.burst_plan("kelly", "2026-12-07", cfg=pinned)["bursts"][0]

        s_local = rq._parse_iso(summer["start"]).astimezone(ny).strftime("%H:%M")
        w_local = rq._parse_iso(winter["start"]).astimezone(ny).strftime("%H:%M")
        assert s_local == w_local == "08:05", (s_local, w_local)

        assert summer["start"][11:16] == "12:05", summer["start"]   # EDT, UTC-4
        assert winter["start"][11:16] == "13:05", winter["start"]   # EST, UTC-5

    def test_a_second_zone_lands_on_its_own_local_clock(self, cfg):
        """Same pinned window, different zone: the UTC instant must move by the
        offset, which is what proves the zone is read rather than decorative."""
        hk = rq.burst_plan("cici", "2026-08-03",
                           cfg=self._pinned(cfg, tz="Asia/Hong_Kong"))["bursts"][0]
        assert hk["start"][11:16] == "00:05", hk["start"]  # HKT, UTC+8

    def test_cici_sessions_replace_the_fleet_map(self, cfg):
        """Her override REPLACES rather than merges. A merge would leave her
        awake for the New York close — the "replying at 3am in its own time
        zone" tell the runbook asks a human to avoid."""
        assert rq.pacing_for(cfg, "cici")["tz"] == "Asia/Hong_Kong"
        us = rq.pacing_for(cfg, "kelly")["sessions"]
        hk = rq.pacing_for(cfg, "cici")["sessions"]
        assert set(hk) == set(us), "session NAMES should still line up"
        assert hk != us, "cici inherited the US windows"

    def test_cici_never_shares_a_burst_minute_with_a_us_desk(self, cfg):
        for i in range(30):
            day = (datetime(2026, 8, 3, tzinfo=timezone.utc) + timedelta(days=i)).strftime("%Y-%m-%d")
            hk = [(rq._parse_iso(b["start"]), rq._parse_iso(b["end"]))
                  for b in _live_bursts(rq.burst_plan("cici", day, cfg=cfg))]
            for account in ("kelly", "sophia", "meagan", "flagship"):
                for b in _live_bursts(rq.burst_plan(account, day, cfg=cfg)):
                    s, e = rq._parse_iso(b["start"]), rq._parse_iso(b["end"])
                    for hs, he in hk:
                        assert not (s < he and hs < e), (
                            f"{day}: cici overlaps {account} — sessions collapsed")

    def test_an_unknown_timezone_warns_and_falls_back(self, cfg, capsys):
        broken = json.loads(json.dumps(cfg))
        broken["reply_desk"]["pacing"]["tz"] = "Mars/Olympus_Mons"
        rq.burst_plan("kelly", "2026-08-03", cfg=broken)
        line = capsys.readouterr().out.strip().splitlines()[0]
        assert line.startswith("::warning title=reply-pacing-tz::")


# ===========================================================================
# GATE 3: pacing is off unless the config says otherwise, and the SHIPPED
#         config says otherwise
# ===========================================================================
class TestPacingArming:
    def test_in_code_default_is_off(self):
        """An ad-hoc `{"reply_desk": {...}}` dict in a script or a test must
        never be silently burst-gated by a rule it does not declare."""
        assert rq.PACING_DEFAULTS["enabled"] is False
        assert rq.pacing_for({"reply_desk": {}}, "kelly")["enabled"] is False

    def test_the_shipped_config_turns_it_on(self, cfg):
        """This assertion, not the in-code default, is what stops pacing from
        shipping dark. Deleting the config key must go red here."""
        assert cfg["reply_desk"]["pacing"]["enabled"] is True
        assert rq.pacing_for(cfg, "kelly")["enabled"] is True

    def test_disabled_pacing_leaves_may_send_untouched(self, cfg, store):
        off = json.loads(json.dumps(cfg))
        off["reply_desk"]["mode"]["accounts"]["kelly"] = "M1"
        off["reply_desk"]["pacing"]["enabled"] = False
        gate = rq.may_send("kelly", cfg=off, root=store,
                           now=datetime(2026, 8, 3, 4, 0, tzinfo=timezone.utc))
        assert gate["ok"] is True and gate["held_by"] is None
        assert gate["cap"] == gate["cap_daily"] == 18

    def test_account_overrides_fill_rather_than_erase_scalar_blocks(self, cfg):
        tuned = json.loads(json.dumps(cfg))
        tuned["reply_desk"]["pacing"]["accounts"]["kelly"] = {"bursts_per_day": {"max": 3}}
        p = rq.pacing_for(tuned, "kelly")
        assert p["bursts_per_day"] == {"min": 2, "max": 3}, "a partial override erased `min`"


# ===========================================================================
# GATE 4: the burst gate binds, and names the cap that bound
# ===========================================================================
class TestBurstGate:
    def test_a_send_inside_a_burst_is_allowed(self, m1, store):
        day, plan = _first_active_day(m1)
        inside = rq._parse_iso(_live_bursts(plan)[0]["start"]) + timedelta(minutes=1)
        gate = rq.may_send("kelly", cfg=m1, root=store, now=inside)
        assert gate["ok"] is True, gate
        assert gate["held_by"] is None

    def test_a_send_between_bursts_is_held_and_the_cap_is_named(self, m1, store):
        day, plan = _first_active_day(m1)
        outside = rq._parse_iso(_live_bursts(plan)[0]["start"]) - timedelta(minutes=30)
        gate = rq.may_send("kelly", cfg=m1, root=store, now=outside)
        assert gate["ok"] is False
        assert gate["held_by"] == "burst_window"
        assert gate["reason"] == "outside_burst"
        assert "next one opens at" in gate["pacing"]["note"]

    def test_the_effective_cap_collapses_headroom_outside_a_burst(self, m1, store):
        """This is what makes burst discipline bind in the export lane without
        that lane knowing pacing exists: it sizes headroom as
        `cap - sent - in_flight`, so an effective cap equal to `sent` exports
        nothing. The raw dial stays visible as `cap_daily`."""
        day, plan = _first_active_day(m1)
        outside = rq._parse_iso(_live_bursts(plan)[0]["start"]) - timedelta(minutes=30)
        gate = rq.may_send("kelly", cfg=m1, root=store, now=outside)
        assert gate["cap"] == gate["sent"] == 0
        assert gate["cap_daily"] == 18

    def test_a_spent_burst_is_held_as_burst_capacity_not_burst_window(self, m1, store):
        day, plan = _first_active_day(m1)
        burst = _live_bursts(plan)[0]
        start = rq._parse_iso(burst["start"])
        for i in range(int(burst["items"])):
            _send_one(store, m1, now=start + timedelta(seconds=10 * (i + 1)),
                      thread=f"19000000000000010{i:02d}", author=f"author{i}")
        gate = rq.may_send("kelly", cfg=m1, root=store,
                           now=start + timedelta(minutes=1))
        assert gate["ok"] is False
        assert gate["held_by"] == "burst_capacity", gate
        assert gate["reason"] == "burst_full"

    def test_every_reported_cap_name_is_declared(self, m1, store):
        day, plan = _first_active_day(m1)
        outside = rq._parse_iso(_live_bursts(plan)[0]["start"]) - timedelta(minutes=30)
        pace = rq.pacing_gate("kelly", cfg=m1, root=store, now=outside)
        for check in pace["checks"]:
            assert check["cap"] in rq.CAP_NAMES, check


def _send_one(store: Path, cfg: dict, *, now: datetime, thread: str,
              author: str = "somequant", account: str = "kelly") -> str:
    """Enqueue -> approve -> claim -> sent, so the ledger carries a real send."""
    item = _item(account=account, thread=thread, author=author,
                 draft=f"{DRAFT} {thread}", now=now)
    res = rq.enqueue(item, store, cfg=cfg, now=now)
    assert res["ok"], res
    assert rq.approve(item["id"], root=store)
    assert rq.claim(item["id"], holder="desk-1", root=store, now=now) is not None
    out = rq.mark_sent(item["id"], receipt={"url": "u"}, root=store, cfg=cfg, now=now)
    assert out["ok"], out
    return item["id"]


# ===========================================================================
# GATE 5: the weekly cap
# ===========================================================================
class TestWeeklyCap:
    def test_the_weekly_cap_holds_and_names_itself(self, m1, store):
        tight = json.loads(json.dumps(m1))
        tight["reply_desk"]["pacing"]["per_account_weekly"] = 2
        day, plan = _first_active_day(tight)
        start = rq._parse_iso(_live_bursts(plan)[0]["start"])
        # Two sends three days back — inside the rolling window, outside today.
        for i in range(2):
            _send_one(store, tight, now=start - timedelta(days=3, minutes=i),
                      thread=f"19000000000000020{i:02d}", author=f"prior{i}")
        gate = rq.may_send("kelly", cfg=tight, root=store, now=start + timedelta(minutes=1))
        assert gate["ok"] is False
        assert gate["held_by"] == "weekly_cap"
        assert gate["reason"] == "reply_cap_weekly"

    def test_the_window_rolls_rather_than_resetting_on_a_calendar_boundary(self, m1, store):
        """A calendar week resets on a boundary the account cannot feel, so a
        Sunday-Monday double spend passes it while looking like a burnout."""
        tight = json.loads(json.dumps(m1))
        tight["reply_desk"]["pacing"]["per_account_weekly"] = 2
        day, plan = _first_active_day(tight)
        start = rq._parse_iso(_live_bursts(plan)[0]["start"])
        for i in range(2):
            _send_one(store, tight, now=start - timedelta(days=8, minutes=i),
                      thread=f"19000000000000021{i:02d}", author=f"old{i}")
        gate = rq.may_send("kelly", cfg=tight, root=store, now=start + timedelta(minutes=1))
        assert gate["ok"] is True, "sends 8 days back must have aged out of the window"


# ===========================================================================
# GATE 6: pacing governs what we START, never what we RECORD
# ===========================================================================
class TestPacingNeverBlocksARecordedSend:
    def test_mark_sent_ignores_the_burst_window(self, m1, store):
        """A receipt means the reply is already PUBLIC. Refusing it would trade
        a pacing miss we cannot undo for a bookkeeping hole we also cannot undo:
        `reply_export.ingest_receipts` retires an unrecognised refusal to
        `.unresolved` and the send leaves the ledger forever, which makes the
        daily and weekly counters under-read from then on."""
        day, plan = _first_active_day(m1)
        outside = rq._parse_iso(_live_bursts(plan)[0]["start"]) - timedelta(minutes=45)
        assert rq.may_send("kelly", cfg=m1, root=store, now=outside)["ok"] is False
        sent_id = _send_one(store, m1, now=outside, thread="1900000000000003001",
                            author="lateauthor")
        assert rq.fold_state(store)["status"][sent_id] == "sent"

    def test_mark_sent_still_honours_the_daily_cap(self, m1, store):
        """`enforce_pacing=False` must drop pacing only — the pre-existing
        authorities stay exactly where they were."""
        capped = json.loads(json.dumps(m1))
        capped["reply_desk"]["daily_caps"]["accounts"]["kelly"] = 1
        day, plan = _first_active_day(capped)
        start = rq._parse_iso(_live_bursts(plan)[0]["start"])
        _send_one(store, capped, now=start, thread="1900000000000004001", author="a1")
        item = _item(thread="1900000000000004002", author="a2", now=start,
                     draft=DRAFT + " second")
        assert rq.enqueue(item, store, cfg=capped, now=start)["ok"]
        assert rq.approve(item["id"], root=store)
        assert rq.claim(item["id"], holder="desk-1", root=store, now=start) is not None
        out = rq.mark_sent(item["id"], receipt={"url": "u"}, root=store, cfg=capped, now=start)
        assert out["ok"] is False and out["reason"] == "reply_cap_daily"


# ===========================================================================
# GATE 7: the two per-target floors, enforced at enqueue
# ===========================================================================
class TestSameAuthorFloor:
    def test_a_second_reply_to_one_author_is_refused_inside_the_floor(self, cfg, store):
        now = datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)
        first = _item(thread="1900000000000005001", author="somequant", now=now)
        assert rq.enqueue(first, store, cfg=cfg, now=now)["ok"]
        soon = now + timedelta(minutes=45)
        second = _item(thread="1900000000000005002", author="somequant", now=soon,
                       draft=DRAFT + " again")
        res = rq.enqueue(second, store, cfg=cfg, now=soon)
        assert res["ok"] is False
        assert res["reason"] == res["held_by"] == "same_author_floor"
        assert "the floor is 360 min" in res["note"]

    def test_the_floor_clears_once_it_has_actually_passed(self, cfg, store):
        now = datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)
        assert rq.enqueue(_item(thread="1900000000000005011", author="somequant", now=now),
                          store, cfg=cfg, now=now)["ok"]
        later = now + timedelta(minutes=361)
        res = rq.enqueue(_item(thread="1900000000000005012", author="somequant",
                               now=later, draft=DRAFT + " later"),
                         store, cfg=cfg, now=later)
        assert res["ok"] is True, res

    def test_an_expired_draft_does_not_hold_the_author_hostage(self, cfg, store):
        """Nobody ever saw an expired draft, so it must not lock an author out
        for six hours. This is the same live/dead split the one-owner lock uses."""
        now = datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)
        first = _item(thread="1900000000000005021", author="somequant", now=now, ttl_min=45)
        assert rq.enqueue(first, store, cfg=cfg, now=now)["ok"]
        later = now + timedelta(minutes=60)
        assert first["id"] in rq.expire_due(now=later, root=store)
        res = rq.enqueue(_item(thread="1900000000000005022", author="somequant",
                               now=later, draft=DRAFT + " fresh"),
                         store, cfg=cfg, now=later)
        assert res["ok"] is True, res

    def test_a_different_author_is_unaffected(self, cfg, store):
        now = datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)
        assert rq.enqueue(_item(thread="1900000000000005031", author="somequant", now=now),
                          store, cfg=cfg, now=now)["ok"]
        soon = now + timedelta(minutes=5)
        res = rq.enqueue(_item(thread="1900000000000005032", author="otherquant",
                               now=soon, draft=DRAFT + " other"),
                         store, cfg=cfg, now=soon)
        assert res["ok"] is True, res


class TestConversationCap:
    """The one-owner lock only sees LIVE items, so a conversation whose draft
    expired is unlocked again — and again. Nothing else in the store bounds
    "we tried to get into this thread nine times today"."""

    @pytest.fixture()
    def no_floor(self, cfg) -> dict:
        out = json.loads(json.dumps(cfg))
        out["reply_desk"]["pacing"]["min_minutes_between_same_author"] = 0
        return out

    def test_a_third_entry_into_one_conversation_is_refused(self, no_floor, store):
        now = datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)
        thread = "1900000000000006001"
        for i in range(2):
            when = now + timedelta(minutes=60 * i)
            item = _item(thread=thread, now=when, draft=f"{DRAFT} take {i}")
            assert rq.enqueue(item, store, cfg=no_floor, now=when)["ok"], i
            rq.expire_due(now=when + timedelta(minutes=50), root=store)
        when = now + timedelta(minutes=180)
        res = rq.enqueue(_item(thread=thread, now=when, draft=f"{DRAFT} take 3"),
                         store, cfg=no_floor, now=when)
        assert res["ok"] is False
        assert res["reason"] == res["held_by"] == "conversation_cap"
        assert "the cap is 2" in res["note"]

    def test_the_cap_counts_dead_entries_too(self, no_floor, store):
        """Counting only live items would make this cap a restatement of the
        one-owner lock, which already refuses those."""
        now = datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)
        thread = "1900000000000006011"
        item = _item(thread=thread, now=now)
        assert rq.enqueue(item, store, cfg=no_floor, now=now)["ok"]
        rq.expire_due(now=now + timedelta(minutes=60), root=store)
        state = rq.fold_state(store)
        assert state["status"][item["id"]] == "expired"
        assert rq._conversation_entries("kelly", thread, state) == 1


# ===========================================================================
# GATE 8: the desk can say WHY
# ===========================================================================
class TestHoldsAreRecorded:
    def test_a_held_send_writes_a_named_hold_row(self, m1, store):
        day, plan = _first_active_day(m1)
        outside = rq._parse_iso(_live_bursts(plan)[0]["start"]) - timedelta(minutes=30)
        rq.may_send("kelly", cfg=m1, root=store, now=outside)
        rows = rq.pacing_holds(store)
        assert len(rows) == 1
        assert rows[0]["held_by"] == "burst_window"
        assert rows[0]["account"] == "kelly"
        assert rows[0]["checks"], "a hold with no checks cannot explain itself"

    def test_identical_holds_are_deduplicated_within_a_day(self, m1, store):
        """The fastlane daemon ticks every ~75s. An undeduplicated hold row
        writes a thousand identical lines a day and buries the one transition
        an operator cares about."""
        day, plan = _first_active_day(m1)
        outside = rq._parse_iso(_live_bursts(plan)[0]["start"]) - timedelta(minutes=30)
        for i in range(5):
            rq.may_send("kelly", cfg=m1, root=store, now=outside + timedelta(seconds=75 * i))
        assert len(rq.pacing_holds(store)) == 1

    def test_a_changed_cap_writes_a_new_row(self, m1, store):
        tight = json.loads(json.dumps(m1))
        tight["reply_desk"]["pacing"]["per_account_weekly"] = 2
        day, plan = _first_active_day(tight)
        start = rq._parse_iso(_live_bursts(plan)[0]["start"])
        rq.may_send("kelly", cfg=tight, root=store, now=start - timedelta(minutes=30))
        for i in range(2):
            _send_one(store, tight, now=start - timedelta(days=3, minutes=i),
                      thread=f"19000000000000070{i:02d}", author=f"prior{i}")
        rq.may_send("kelly", cfg=tight, root=store, now=start + timedelta(minutes=1))
        held = [r["held_by"] for r in rq.pacing_holds(store)]
        assert held == ["burst_window", "weekly_cap"], held

    def test_a_refused_enqueue_records_the_item_id(self, cfg, store):
        now = datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)
        assert rq.enqueue(_item(thread="1900000000000008001", author="somequant", now=now),
                          store, cfg=cfg, now=now)["ok"]
        soon = now + timedelta(minutes=10)
        second = _item(thread="1900000000000008002", author="somequant", now=soon,
                       draft=DRAFT + " dup")
        rq.enqueue(second, store, cfg=cfg, now=soon)
        rows = rq.pacing_holds(store)
        assert [r["held_by"] for r in rows] == ["same_author_floor"]
        assert rows[0]["id"] == second["id"], "a hold with no item id cannot be traced"

    def test_holds_can_be_read_back_for_one_day(self, m1, store):
        day, plan = _first_active_day(m1)
        outside = rq._parse_iso(_live_bursts(plan)[0]["start"]) - timedelta(minutes=30)
        rq.may_send("kelly", cfg=m1, root=store, now=outside)
        assert rq.pacing_holds(store, day=day)
        assert rq.pacing_holds(store, day="1999-01-01") == []
