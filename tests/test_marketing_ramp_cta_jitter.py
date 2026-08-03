"""tests/test_marketing_ramp_cta_jitter.py — cold-account posting posture.

Three knobs shipped together because they answer one question: what may a
BRAND-NEW X account do?  All writes go to tmp_path — never repo data/
(MM_DATA_GUARD tripwire).

Coverage:
  A. sentinel.resolve_ramp_tier — the age→tier table, including every boundary
     day (13/14, 27/28, 55/56) and the graduated passthrough.
  B. a missing `created:` on an ENABLED account fails closed to weeks_1_2 AND
     prints a line-start ::warning (capsys, not caplog — a logger would prefix
     the line and GitHub would drop it).
  C. the stricter-of merge law: base -1 + tier 2 ⇒ 2; base links false + tier
     true ⇒ false; min_minutes takes the max.
  D. theme_list quarantined with reason ramp_theme_list on a week-1 account,
     clean on a graduated one.
  E. the publish-time auto-approve lane refuses to generate a theme_list for a
     week-1 account (it auto-approves its own output — it must not route around
     the plan-tier gate).
  F. cashtag breadth 2 enforced on a week-1 account's non-theme post.
  G. publish.chart_cta_enabled — false renders the footer without the trial
     button but keeps the URL lockup; the CTA-on path stays byte-identical to
     the no-kwarg default.
  H. send-time jitter — deterministic per item id, bounded by the config max,
     the floor advances by the BOOKED time, and immediate items are untouched.
"""
from __future__ import annotations

import zlib
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

_AS_OF = "2026-07-27"

# An outbox id whose crc32 residue is a PROVABLY NON-ZERO jitter offset. Every
# jitter assertion below is written against this literal rather than against a
# re-derivation of the function under test — an id with offset 0 makes the whole
# suite pass with jitter switched off, which is exactly how the first round of
# these tests shipped vacuous.
_JITTER_ID = "it-jitter-4"
_JITTER_OFFSET = zlib.crc32(_JITTER_ID.encode("utf-8")) % 8   # == 7 at max 7


@pytest.fixture(autouse=True)
def _fresh_annotations():
    """sentinel emits each ramp ``::warning`` at most once per PROCESS (so one
    publisher sweep does not print the same config defect six times). Under
    pytest the whole file is one process, so without this reset the first test to
    trip a warning would silence every later test asserting on the same one."""
    from engine.marketing.sentinel import reset_ramp_announcements
    reset_ramp_announcements()
    yield
    reset_ramp_announcements()

_RAMP_TABLE: dict[str, Any] = {
    "graduate_after_days": 56,
    "weeks_1_2": {
        "max_posts_per_account_per_day": 2,
        "min_minutes_between_posts": 45,
        "links_allowed": False,
        "max_media_posts_per_account_per_day": 1,
        "max_same_cashtag_per_account_per_day": 1,
        "max_replies_per_account_per_day": 0,
        "max_new_follows_per_account_per_day": 0,
        "max_cashtags_per_post": 2,
        "theme_list_allowed": False,
    },
    "weeks_3_4": {
        "max_posts_per_account_per_day": 3,
        "min_minutes_between_posts": 45,
        "links_allowed": False,
        "max_media_posts_per_account_per_day": 2,
        "max_same_cashtag_per_account_per_day": 2,
        "max_replies_per_account_per_day": 0,
        "max_new_follows_per_account_per_day": 0,
        "max_cashtags_per_post": 2,
        "theme_list_allowed": False,
    },
    "week_5_plus": {
        "max_posts_per_account_per_day": 4,
        "min_minutes_between_posts": 45,
        "links_allowed": True,
        "max_media_posts_per_account_per_day": 3,
        "max_same_cashtag_per_account_per_day": 2,
        "max_replies_per_account_per_day": 2,
        "max_new_follows_per_account_per_day": 5,
        "max_cashtags_per_post": 3,
        "theme_list_allowed": True,
    },
}


def _cfg(*, accounts: list[dict], ramp: dict | None = None,
         base_overrides: dict | None = None) -> dict:
    """A marketing cfg mirroring the LIVE base block (unlimited volume, no links)."""
    sentinel_block: dict[str, Any] = {
        "near_dup_jaccard": 0.50,
        "max_posts_per_account_per_day": -1,          # unlimited (operator 2026-07-24)
        "max_media_posts_per_account_per_day": -1,    # unlimited
        "max_same_cashtag_per_account_per_day": 1,
        "max_replies_per_account_per_day": 0,
        "max_new_follows_per_account_per_day": 0,
        "max_receipt_age_days": 7,
        "min_minutes_between_posts": 45,
        "links_allowed": False,
        "max_cashtags_per_post": 3,
        "require_signal_disclosure": False,
        "lexicon_phrases": [],
        "lexicon_patterns": [],
    }
    sentinel_block.update(base_overrides or {})
    if ramp is not None:
        sentinel_block["ramp"] = ramp
    return {
        "settings": {"auditor_strict": True},
        "sentinel": sentinel_block,
        "desk_network": {"stage": "A", "accounts": accounts},
    }


def _acct(acc_id: str, *, created: str | None = None, enabled: bool = True) -> dict:
    out: dict[str, Any] = {"id": acc_id, "kind": "branded",
                           "voice": "authoritative desk", "enabled": enabled}
    if created is not None:
        out["created"] = created
    return out


def _item(iid: str, *, type: str = "signal", headline: str = "A clean headline",
          body: str = "Plain body copy.", cashtag: str = "$AAPL",
          slot: str | None = None, chart_id: str | None = None) -> dict:
    out: dict[str, Any] = {
        "id": iid, "type": type, "headline": headline, "body": body,
        "cashtag": cashtag, "ticker": cashtag.lstrip("$"),
        "status": "drafted", "provenance": "test", "slot": slot or f"D1-{iid}",
    }
    if chart_id is not None:
        out["chart_id"] = chart_id
    return out


def _plan(queues: dict[str, list[dict]], as_of: str = _AS_OF) -> dict:
    return {
        "schema_version": 1,
        "produced_by": "test",
        "produced_at": f"{as_of}T00:00:00Z",
        "as_of": as_of,
        "accounts": [{"id": aid, "queue": items} for aid, items in queues.items()],
    }


def _reasons(report: dict, item_id: str) -> list[str]:
    for row in report["quarantined"]:
        if row["id"] == item_id:
            return row["reasons"]
    return []


def _minus(days: int, as_of: str = _AS_OF) -> str:
    """The created: date that makes an account exactly `days` old at as_of."""
    return (date.fromisoformat(as_of) - timedelta(days=days)).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# A. Tier resolution table (boundaries are the whole point)
# ─────────────────────────────────────────────────────────────────────────────

class TestRampTierTable:

    @pytest.mark.parametrize("age_days,expected", [
        (0, "weeks_1_2"),
        (1, "weeks_1_2"),
        (13, "weeks_1_2"),     # boundary: last day of tier 1
        (14, "weeks_3_4"),     # boundary: first day of tier 2
        (27, "weeks_3_4"),     # boundary: last day of tier 2
        (28, "week_5_plus"),   # boundary: first day of tier 3
        (55, "week_5_plus"),   # boundary: last ramped day
        (56, "graduated"),     # boundary: graduate_after_days
        (400, "graduated"),
    ])
    def test_age_maps_to_tier(self, age_days: int, expected: str):
        from engine.marketing.sentinel import resolve_ramp_tier
        assert resolve_ramp_tier(_minus(age_days), _AS_OF) == expected

    def test_graduate_after_days_is_configurable(self):
        from engine.marketing.sentinel import resolve_ramp_tier
        assert resolve_ramp_tier(_minus(30), _AS_OF, graduate_after_days=29) == "graduated"
        assert resolve_ramp_tier(_minus(30), _AS_OF, graduate_after_days=31) == "week_5_plus"

    @pytest.mark.parametrize("created", [None, "", "not-a-date", "2026-13-45"])
    def test_unusable_created_fails_closed(self, created):
        from engine.marketing.sentinel import resolve_ramp_tier
        assert resolve_ramp_tier(created, _AS_OF) == "weeks_1_2"

    def test_future_created_fails_closed(self):
        """A created: date after as_of is corrupt data, not a very old account."""
        from engine.marketing.sentinel import resolve_ramp_tier
        assert resolve_ramp_tier("2027-01-01", _AS_OF) == "weeks_1_2"

    def test_missing_as_of_fails_closed(self):
        from engine.marketing.sentinel import resolve_ramp_tier
        assert resolve_ramp_tier("2020-01-01", "") == "weeks_1_2"

    def test_iso_timestamp_created_is_accepted(self):
        from engine.marketing.sentinel import resolve_ramp_tier
        assert resolve_ramp_tier(f"{_minus(30)}T12:00:00Z", _AS_OF) == "week_5_plus"

    def test_graduated_account_keeps_base_caps_untouched(self):
        """The 2026-07-24 unlimited-cadence ruling still governs a warmed desk."""
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("warm", created=_minus(200))], ramp=_RAMP_TABLE)
        caps = resolve_ramp(cfg, _AS_OF)["accounts"]["warm"]["caps"]
        assert caps["max_posts_per_account_per_day"] is None      # unlimited
        assert caps["max_media_posts_per_account_per_day"] is None
        assert caps["max_cashtags_per_post"] == 3
        assert caps["theme_list_allowed"] is True

    def test_absent_ramp_table_is_a_no_op(self):
        """No sentinel.ramp in cfg ⇒ nothing enforced, base caps everywhere."""
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("cold", created=_minus(1))])
        ramp = resolve_ramp(cfg, _AS_OF)
        assert ramp["enforced"] is False
        assert ramp["accounts"]["cold"]["tier"] == "graduated"
        assert ramp["accounts"]["cold"]["caps"]["max_posts_per_account_per_day"] is None


# ─────────────────────────────────────────────────────────────────────────────
# B. Missing created: → weeks_1_2 + a line-start ::warning
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingCreatedAnnotation:

    def test_enabled_account_without_created_gets_weeks_1_2(self, capsys):
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("nodate")], ramp=_RAMP_TABLE)
        ramp = resolve_ramp(cfg, _AS_OF)
        assert ramp["accounts"]["nodate"]["tier"] == "weeks_1_2"
        assert ramp["missing_created"] == ["nodate"]
        caps = ramp["accounts"]["nodate"]["caps"]
        assert caps["max_posts_per_account_per_day"] == 2
        assert caps["max_cashtags_per_post"] == 2
        assert caps["theme_list_allowed"] is False

        # The annotation must reach the Actions summary, which means it must be
        # the FIRST thing on its line — a logger would prefix it and GitHub would
        # silently drop it (tests/test_gh_annotation_line_start.py).
        out = capsys.readouterr().out
        hits = [ln for ln in out.splitlines() if "sentinel-ramp-created-missing" in ln]
        assert hits, f"expected a ::warning annotation, got stdout: {out!r}"
        assert hits[0].startswith("::"), f"annotation not at line start: {hits[0]!r}"
        assert "nodate" in hits[0]

    def test_disabled_account_without_created_is_not_annotated(self, capsys):
        """A planned desk with no X account behind it is not a config defect."""
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("planned", enabled=False)], ramp=_RAMP_TABLE)
        ramp = resolve_ramp(cfg, _AS_OF)
        assert ramp["missing_created"] == []
        assert "sentinel-ramp-created-missing" not in capsys.readouterr().out

    def test_announce_false_silences_the_annotation(self, capsys):
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("nodate")], ramp=_RAMP_TABLE)
        ramp = resolve_ramp(cfg, _AS_OF, announce=False)
        assert ramp["missing_created"] == ["nodate"]
        assert "::warning" not in capsys.readouterr().out

    def test_gate_plan_reports_and_notes_the_missing_date(self, capsys):
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("nodate")], ramp=_RAMP_TABLE)
        plan = _plan({"nodate": [_item("i1")]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert report["checks"]["ramp"]["missing_created"] == ["nodate"]
        assert any("nodate" in n and "fail-closed" in n for n in report["notes"])
        assert capsys.readouterr().out.startswith("::warning")


# ─────────────────────────────────────────────────────────────────────────────
# C. Stricter-of merge law
# ─────────────────────────────────────────────────────────────────────────────

class TestStricterOfMerge:

    def _caps(self, *, created: str, base_overrides: dict | None = None,
              ramp: dict | None = None) -> dict:
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("a", created=created)],
                   ramp=ramp if ramp is not None else _RAMP_TABLE,
                   base_overrides=base_overrides)
        return resolve_ramp(cfg, _AS_OF)["accounts"]["a"]["caps"]

    def test_unlimited_base_yields_to_a_bounded_tier(self):
        """base -1 (unlimited) + tier 2 ⇒ 2. Unlimited is the LOOSEST value."""
        caps = self._caps(created=_minus(1))
        assert caps["max_posts_per_account_per_day"] == 2
        assert caps["max_media_posts_per_account_per_day"] == 1

    def test_bounded_base_wins_when_it_is_stricter(self):
        """A tier row may never LOOSEN a base cap the operator already tightened."""
        caps = self._caps(created=_minus(30),   # week_5_plus: 4 posts/day
                          base_overrides={"max_posts_per_account_per_day": 1})
        assert caps["max_posts_per_account_per_day"] == 1

    def test_unlimited_tier_never_loosens_a_bounded_base(self):
        ramp = {"graduate_after_days": 56,
                "weeks_1_2": {"max_posts_per_account_per_day": -1}}
        caps = self._caps(created=_minus(1), ramp=ramp,
                          base_overrides={"max_posts_per_account_per_day": 3})
        assert caps["max_posts_per_account_per_day"] == 3

    def test_links_allowed_is_a_logical_and(self):
        """base false + tier true ⇒ false (week_5_plus re-allows links; base says no)."""
        caps = self._caps(created=_minus(30))
        assert caps["links_allowed"] is False

    def test_links_allowed_true_and_true_is_true(self):
        caps = self._caps(created=_minus(30), base_overrides={"links_allowed": True})
        assert caps["links_allowed"] is True

    def test_links_allowed_true_base_false_tier_is_false(self):
        caps = self._caps(created=_minus(1), base_overrides={"links_allowed": True})
        assert caps["links_allowed"] is False

    def test_min_minutes_between_posts_takes_the_max(self):
        """The LONGER wait wins, whichever side names it."""
        caps = self._caps(created=_minus(1),
                          base_overrides={"min_minutes_between_posts": 90})
        assert caps["min_minutes_between_posts"] == 90
        caps = self._caps(created=_minus(1),
                          base_overrides={"min_minutes_between_posts": 10})
        assert caps["min_minutes_between_posts"] == 45

    def test_partial_tier_row_narrows_only_what_it_names(self):
        ramp = {"graduate_after_days": 56, "weeks_1_2": {"max_cashtags_per_post": 1}}
        caps = self._caps(created=_minus(1), ramp=ramp)
        assert caps["max_cashtags_per_post"] == 1
        assert caps["max_posts_per_account_per_day"] is None   # untouched: unlimited

    def test_quoted_false_does_not_enable_a_policy(self):
        """A YAML string must never re-open links (D08 R2 is a bool, strictly)."""
        ramp = {"graduate_after_days": 56, "weeks_1_2": {"links_allowed": "false"}}
        caps = self._caps(created=_minus(1), ramp=ramp,
                          base_overrides={"links_allowed": True})
        assert caps["links_allowed"] is False


# ─────────────────────────────────────────────────────────────────────────────
# D. Plan-tier enforcement through gate_plan
# ─────────────────────────────────────────────────────────────────────────────

class TestGatePlanRampEnforcement:

    def test_week_one_account_trimmed_to_two_posts_a_day(self):
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("cold", created=_minus(3))], ramp=_RAMP_TABLE)
        plan = _plan({"cold": [
            _item("c1", cashtag="$AAA", slot="D1-a"),
            _item("c2", cashtag="$BBB", slot="D1-b"),
            _item("c3", cashtag="$CCC", slot="D1-c"),
        ]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert report["counts"]["passed"] == 2
        assert "cadence_cap_daily" in _reasons(report, "c3")

    def test_graduated_account_is_untouched_in_the_same_plan(self):
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("cold", created=_minus(3)),
                             _acct("warm", created=_minus(200))], ramp=_RAMP_TABLE)
        plan = _plan({
            "cold": [_item("c1", cashtag="$AAA", slot="D1-a"),
                     _item("c2", cashtag="$BBB", slot="D1-b"),
                     _item("c3", cashtag="$CCC", slot="D1-c")],
            "warm": [_item("w1", cashtag="$DDD", slot="D1-d",
                           headline="Warm one", body="Warm desk body one."),
                     _item("w2", cashtag="$EEE", slot="D1-e",
                           headline="Warm two", body="Warm desk body two."),
                     _item("w3", cashtag="$FFF", slot="D1-f",
                           headline="Warm three", body="Warm desk body three.")],
        })
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert _reasons(report, "c3") and "cadence_cap_daily" in _reasons(report, "c3")
        for iid in ("w1", "w2", "w3"):
            assert not _reasons(report, iid), f"{iid} should pass on a graduated desk"
        tiers = {a: e["tier"] for a, e in report["checks"]["ramp"]["accounts"].items()}
        assert tiers == {"cold": "weeks_1_2", "warm": "graduated"}

    def test_theme_list_quarantined_on_a_week_one_account(self):
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("cold", created=_minus(3))], ramp=_RAMP_TABLE)
        plan = _plan({"cold": [_item(
            "t1", type="theme_list", cashtag="$AAA", slot="D1-t",
            body="$AAA $BBB $CCC $DDD all moved together today.")]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert "ramp_theme_list" in _reasons(report, "t1")
        assert report["checks"]["ramp"]["theme_list_hits"] == 1

    def test_theme_list_is_a_policy_flag_not_a_capacity_trim(self):
        from engine.marketing.sentinel import reason_class
        assert reason_class("ramp_theme_list") == "policy"

    def test_theme_list_passes_on_a_graduated_account(self):
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("warm", created=_minus(200))], ramp=_RAMP_TABLE)
        plan = _plan({"warm": [_item(
            "t1", type="theme_list", cashtag="$AAA", slot="D1-t",
            body="$AAA $BBB $CCC $DDD all moved together today.")]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert not _reasons(report, "t1")
        assert report["checks"]["ramp"]["theme_list_hits"] == 0

    def test_theme_list_passes_at_week_five(self):
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("mid", created=_minus(30))], ramp=_RAMP_TABLE)
        plan = _plan({"mid": [_item(
            "t1", type="theme_list", cashtag="$AAA", slot="D1-t",
            body="$AAA $BBB $CCC $DDD all moved together today.")]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert not _reasons(report, "t1")

    # F. cashtag breadth on a cold account
    def test_three_cashtags_quarantined_on_a_week_one_account(self):
        """Base allows 3; the weeks_1_2 tier says 2, and stricter wins."""
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("cold", created=_minus(3))], ramp=_RAMP_TABLE)
        plan = _plan({"cold": [_item(
            "b1", cashtag="$AAA", slot="D1-b",
            body="$AAA led, $BBB followed, $CCC lagged.")]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert "cashtag_breadth" in _reasons(report, "b1")

    def test_three_cashtags_pass_on_a_graduated_account(self):
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("warm", created=_minus(200))], ramp=_RAMP_TABLE)
        plan = _plan({"warm": [_item(
            "b1", cashtag="$AAA", slot="D1-b",
            body="$AAA led, $BBB followed, $CCC lagged.")]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert not _reasons(report, "b1")

    def test_link_gate_is_per_account(self):
        """week_5_plus re-allows links, but the base block's false ANDs it away."""
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("mid", created=_minus(30))], ramp=_RAMP_TABLE,
                   base_overrides={"links_allowed": True})
        plan = _plan({"mid": [_item("l1", slot="D1-l",
                                    body="Read more at https://mastermind-x.com/")]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert not _reasons(report, "l1"), "week_5_plus + base true ⇒ links allowed"

        cfg_cold = _cfg(accounts=[_acct("cold", created=_minus(1))], ramp=_RAMP_TABLE,
                        base_overrides={"links_allowed": True})
        plan_cold = _plan({"cold": [_item("l2", slot="D1-l",
                                          body="Read more at https://mastermind-x.com/")]})
        _a, report_cold = gate_plan(plan_cold, cfg_cold, receipts_age_days=1,
                                    graded_window=[])
        assert "link_not_allowed" in _reasons(report_cold, "l2")

    def test_account_absent_from_desk_network_gets_the_strictest_caps(self):
        """A plan account with no config row is a config bug — fail closed."""
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("known", created=_minus(200))], ramp=_RAMP_TABLE)
        plan = _plan({"ghost": [_item("g1", cashtag="$AAA", slot="D1-a"),
                                _item("g2", cashtag="$BBB", slot="D1-b"),
                                _item("g3", cashtag="$CCC", slot="D1-c")]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert "cadence_cap_daily" in _reasons(report, "g3")

    def test_report_carries_the_resolved_tier_per_account(self):
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("cold", created="2026-07-24")], ramp=_RAMP_TABLE)
        plan = _plan({"cold": [_item("c1")]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        block = report["checks"]["ramp"]
        assert block["enforced"] is True
        assert block["graduate_after_days"] == 56
        assert block["as_of"] == _AS_OF
        entry = block["accounts"]["cold"]
        assert entry["created"] == "2026-07-24"
        assert entry["age_days"] == 3
        assert entry["tier"] == "weeks_1_2"
        assert entry["enabled"] is True
        assert entry["caps"]["max_posts_per_account_per_day"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# D-bis. The LIVE config: flagship really is on the ramp
# ─────────────────────────────────────────────────────────────────────────────

class TestLiveConfigRamp:

    @staticmethod
    def _live_cfg() -> dict:
        import yaml
        from pathlib import Path
        return yaml.safe_load(
            (Path(__file__).resolve().parent.parent / "config" / "marketing.yml")
            .read_text(encoding="utf-8")) or {}

    def test_ramp_table_carries_the_enforced_keys(self):
        """Re-pinned 2026-08-03 to the operator's relaxed schedule: graduation at
        21 days, tier boundaries at 5/10 (config-readable since the same order),
        and theme_list allowed from day 0 — the ban was what left kelly with zero
        posts, ever, because her only at-bat was that format (masterplan §8.1 V2).
        The ramp is a platform-risk throttle, so these numbers are an operator
        dial; what this test defends is that the table still CARRIES every key the
        gate enforces."""
        ramp = self._live_cfg()["sentinel"]["ramp"]
        assert ramp["graduate_after_days"] == 21
        assert ramp["weeks_1_2_days"] == 5
        assert ramp["weeks_3_4_days"] == 10
        for tier in ("weeks_1_2", "weeks_3_4", "week_5_plus"):
            assert "max_cashtags_per_post" in ramp[tier]
            assert "theme_list_allowed" in ramp[tier]
        assert ramp["weeks_1_2"]["theme_list_allowed"] is True
        assert ramp["weeks_3_4"]["theme_list_allowed"] is True
        assert ramp["week_5_plus"]["theme_list_allowed"] is True

    def test_every_enabled_live_account_carries_a_created_date(self):
        """Enabled without created: is exactly the defect the annotation shouts
        about — the live config must not be the thing that triggers it."""
        for acc in self._live_cfg()["desk_network"]["accounts"]:
            if acc.get("enabled"):
                assert acc.get("created"), f"{acc['id']} is enabled with no created:"

    def test_flagship_is_ramped_today_not_unlimited(self):
        """Flagship is BOUNDED, and the growth gates it has not earned stay shut.

        Re-pinned 2026-07-28: the operator widened flagship to 20 posts/day at a
        30-minute cadence via sentinel.ramp.account_overrides. The number is a
        policy dial and will move again; what this test defends is the invariant
        that did NOT move — flagship still resolves to a FINITE cap (never the
        base `unlimited`), and the two reputation gates the ramp exists to hold
        shut on a young account are still shut. Asserting the literal 2 made this
        a change-detector for a knob rather than a guard on the contract.
        """
        from engine.marketing.sentinel import resolve_ramp
        entry = resolve_ramp(self._live_cfg(), "2026-07-27")["accounts"]["flagship"]
        caps = entry["caps"]
        n = caps["max_posts_per_account_per_day"]
        assert n is not None, "flagship fell through to the base unlimited cap"
        assert isinstance(n, int) and n > 0
        # links stays a shut reputation gate on a young account. theme_list was
        # operator-granted on 2026-07-28 (live sector lists were 100% dropped on
        # a rout day) — so the invariant is no longer "shut" but ATTRIBUTABLE:
        # if it is open, a named override must say so. An open gate with no
        # recorded override is the merge accident this suite exists to catch.
        assert caps["links_allowed"] is False
        if caps["theme_list_allowed"]:
            assert "theme_list_allowed" in (entry.get("overrides") or {}), (
                "flagship posts theme lists with no recorded override — the "
                "grant must be traceable to sentinel.ramp.account_overrides"
            )

    def test_bool_override_is_parsed_strictly_and_scoped(self):
        """theme_list_allowed / links_allowed overrides: real booleans and the
        six unambiguous strings parse; junk is IGNORED (tier value stands, never
        coerced to False — a typo must not silently revoke); and the grant is
        scoped to the named desk only."""
        from engine.marketing.sentinel import resolve_ramp

        def cfg(override):
            return {
                "sentinel": {"ramp": {
                    "weeks_1_2": {"max_posts_per_account_per_day": 2,
                                  "theme_list_allowed": False},
                    "account_overrides": {"warm": override},
                }},
                "desk_network": {"accounts": [
                    {"id": "warm", "enabled": True, "created": "2026-07-20"},
                    {"id": "cold", "enabled": True, "created": "2026-07-20"},
                ]},
            }

        r = resolve_ramp(cfg({"theme_list_allowed": True}), "2026-07-27",
                         announce=False)["accounts"]
        assert r["warm"]["caps"]["theme_list_allowed"] is True
        assert r["warm"]["overrides"]["theme_list_allowed"] is True
        assert r["cold"]["caps"]["theme_list_allowed"] is False, \
            "the grant leaked past the named desk"

        r = resolve_ramp(cfg({"theme_list_allowed": "true"}), "2026-07-27",
                         announce=False)["accounts"]
        assert r["warm"]["caps"]["theme_list_allowed"] is True

        # A quoted "false" must not enable (the auto_approve parse contract).
        r = resolve_ramp(cfg({"theme_list_allowed": "false"}), "2026-07-27",
                         announce=False)["accounts"]
        assert r["warm"]["caps"]["theme_list_allowed"] is False

        # Junk is ignored: the tier's own value stands and no override records.
        r = resolve_ramp(cfg({"theme_list_allowed": "bananas"}), "2026-07-27",
                         announce=False)["accounts"]
        assert r["warm"]["caps"]["theme_list_allowed"] is False
        assert "theme_list_allowed" not in (r["warm"].get("overrides") or {})

    def test_a_widened_account_says_so_in_the_ramp_report(self):
        """A cap wider than its own tier row must be traceable to a named
        override. An unexplained wide cap on a young account is precisely the
        thing the age ramp exists to make impossible by accident."""
        from engine.marketing.sentinel import resolve_ramp

        resolved = resolve_ramp(self._live_cfg(), "2026-07-27")
        tier_rows = (self._live_cfg().get("sentinel") or {}).get("ramp") or {}
        for acc_id, entry in resolved["accounts"].items():
            if not entry.get("enabled"):
                continue
            tier_row = tier_rows.get(entry["tier"]) or {}
            tier_cap = tier_row.get("max_posts_per_account_per_day")
            cap = entry["caps"]["max_posts_per_account_per_day"]
            if tier_cap is None or cap is None or cap <= tier_cap:
                continue
            assert "max_posts_per_account_per_day" in (entry.get("overrides") or {}), (
                f"{acc_id} resolves to {cap}/day against a tier row of "
                f"{tier_cap}/day with no recorded override — a widened cap must "
                f"be attributable to an operator decision, not to a merge accident"
            )


# ─────────────────────────────────────────────────────────────────────────────
# E. Publish-time lane honours the same tiers
# ─────────────────────────────────────────────────────────────────────────────

class TestPublishTimeLaneRamp:
    """generate_slot_items auto-approves its own output, so it must not be able
    to route around the plan-tier ramp gate.

    Fixture shape mirrors tests/test_marketing_publish_time_content.py: real
    heatmap + snapshot files under tmp_path, an injected `now`, zero network.
    """

    # Monday 2026-07-27, 14:05 UTC == 10:05 ET → the AM slot, mid-session.
    NOW = datetime(2026, 7, 27, 14, 5, 0, tzinfo=timezone.utc)

    @pytest.fixture(autouse=True)
    def _stub_publish_time_card(self, monkeypatch):
        """The publish-time lane now refuses to enqueue a mover/theme item whose
        card cannot be hosted (2026-07-31). These tests are about the RAMP tiers,
        run under tmp_path with no renderer and no R2, so the card is stubbed to
        its happy path and the tier assertions keep measuring the tier."""
        from engine.marketing import publish_time_content as _ptc

        # Keyword-pinned, mirroring the autouse stub in
        # test_marketing_publish_time_content.py: a `lambda cand, **kw` absorbs
        # any signature, so a change to _resolve_card's call contract would be
        # caught in one file and silently swallowed here, leaving the ramp-tier
        # assertions passing against a lane that can no longer resolve a card.
        def _stub_card(cand, *, root, cfg, as_of, now, slot):
            return {
                "media": {"kind": "chart_svg", "chart_id": "stub",
                          "path": "data/marketing/outbox/media/stub.svg",
                          "media_url": "https://cards.example/stub.png"},
                "published": {"chart_id": "stub"}, "reason": "ok"}

        monkeypatch.setattr(_ptc, "_resolve_card", _stub_card)


    @classmethod
    def _write_fixtures(cls, tmp) -> None:
        import json
        md = tmp / "site" / "marketdata"
        md.mkdir(parents=True, exist_ok=True)
        (md / "themes_heatmap.json").write_text(json.dumps({"tiles": [{
            "t": "AI", "name": "Artificial Intelligence", "sector": "AI",
            "perf": {"1D": 0.0},
            "members": [{"t": t, "perf": {"1D": 0.0}}
                        for t in ("NVDA", "AMD", "SMCI", "MU", "AVGO")],
        }]}), encoding="utf-8")
        dm = tmp / "data" / "marketing"
        dm.mkdir(parents=True, exist_ok=True)
        ts_ms = int(cls.NOW.timestamp() * 1000)
        quotes = {"NVDA": (120.0, 117.0, 2.6), "AMD": (150.0, 144.0, 4.2),
                  "SMCI": (40.0, 37.0, 8.1), "MU": (100.0, 96.0, 4.1),
                  "AVGO": (170.0, 165.0, 3.0)}
        (dm / "live_quotes_snapshot.json").write_text(json.dumps({
            "asof": cls.NOW.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "quotes": {t: {"price": p, "prevClose": pc, "changePct": ch, "ts": ts_ms}
                       for t, (p, pc, ch) in quotes.items()},
        }), encoding="utf-8")

    @staticmethod
    def _pt_cfg(created: str) -> dict:
        cfg = _cfg(accounts=[dict(_acct("flagship", created=created),
                                  voice="authoritative desk")],
                   ramp=_RAMP_TABLE)
        cfg["publish"] = {
            "channels": {"flagship": "c1"},
            "publish_time_movers": {
                "enabled": True, "max_per_run": 2,
                "min_abs_mover_pct": 3.0, "min_abs_theme_pct": 1.0,
                "max_quote_age_min": 45,
                # A handful of fixture tiles — pin the flat-tape belt out of the way.
                "min_active_tiles": 1,
            },
        }
        cfg["copywriter"] = {"personas": {"flagship": {
            "name": "The Desk", "voice_notes": "terse. Emoji budget: 0-1"}}}
        return cfg

    def _run(self, tmp_path, created: str) -> dict:
        from engine.marketing import outbox, publish_time_content as ptc
        self._write_fixtures(tmp_path)
        return ptc.generate_slot_items(
            tmp_path, cfg=self._pt_cfg(created), now=self.NOW,
            state=outbox.fold_state(tmp_path), approved_due=[],
            posted_counts={}, cap=2, live=True,
        )

    def test_theme_list_blocked_for_a_week_one_account(self, tmp_path):
        from engine.marketing import outbox
        report = self._run(tmp_path, _minus(3, _AS_OF))
        assert not report.get("generated"), report
        assert not [i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list"]
        reasons = {d["reason"] for d in report.get("dropped", [])}
        assert "ramp_theme_list" in reasons, report

    def test_theme_list_generated_for_a_graduated_account(self, tmp_path):
        from engine.marketing import outbox
        report = self._run(tmp_path, _minus(200, _AS_OF))
        assert report.get("generated"), report
        tl = [i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list"]
        assert tl, report
        reasons = {d["reason"] for d in report.get("dropped", [])}
        assert "ramp_theme_list" not in reasons, report

    def test_lane_reads_the_shared_tier_resolver(self):
        """A regression fence: the lane must not go back to reading the base
        block directly for the per-account caps."""
        import inspect
        from engine.marketing import publish_time_content as ptc
        src = inspect.getsource(ptc.generate_slot_items)
        assert "sentinel.resolve_ramp(" in src
        assert "_DEFAULT_MAX_CASHTAGS_PER_POST" not in src


# ─────────────────────────────────────────────────────────────────────────────
# G. Chart footer CTA
# ─────────────────────────────────────────────────────────────────────────────

def _sample_ohlcv(n: int = 60, base: float = 100.0):
    dates: list[str] = []
    d = date(2026, 1, 2)
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += timedelta(days=1)
    c = [base + i * 0.2 for i in range(n)]
    o = [c[0]] + c[:-1]
    h = [x + 1.0 for x in c]
    lo = [x - 1.0 for x in c]
    v = [1_000_000.0] * n
    return dates, o, h, lo, c, v


_BUTTON_LABEL = "Start free 14-day trial"
_BUTTON_GRADIENT = "bb_btn_"
_URL_LOCKUP = "mastermind-x.com"


class TestChartCtaKnob:

    def test_resolver_defaults_to_on(self):
        from engine.marketing.chart_render import chart_cta_enabled
        assert chart_cta_enabled(None) is True
        assert chart_cta_enabled({}) is True
        assert chart_cta_enabled({"publish": {}}) is True

    def test_resolver_reads_the_knob_strictly(self):
        from engine.marketing.chart_render import chart_cta_enabled
        assert chart_cta_enabled({"publish": {"chart_cta_enabled": False}}) is False
        assert chart_cta_enabled({"publish": {"chart_cta_enabled": "false"}}) is False
        assert chart_cta_enabled({"publish": {"chart_cta_enabled": "true"}}) is True

    def test_live_config_has_the_cta_off(self):
        """Pins the SHIPPED posture, same idiom as the M3 config-drift guard: the
        knob's in-code default is True, so only this assertion records that the
        operator deliberately turned it off. If the operator re-arms the CTA
        post-ramp, flip this line in the same PR — it is a record, not a law."""
        import yaml
        from pathlib import Path
        from engine.marketing.chart_render import chart_cta_enabled
        cfg = yaml.safe_load(
            (Path(__file__).resolve().parent.parent / "config" / "marketing.yml")
            .read_text(encoding="utf-8"))
        assert chart_cta_enabled(cfg) is False

    def test_v2_card_cta_on_is_byte_identical_to_the_default(self):
        """cta=True must be a no-op: the whole family's SVG stays byte-stable."""
        from engine.marketing.chart_render import render_chart_v2
        dates, o, h, lo, c, v = _sample_ohlcv()
        assert render_chart_v2("TEST", dates, o, h, lo, c, v, cta=True) == \
            render_chart_v2("TEST", dates, o, h, lo, c, v)

    def test_v2_card_cta_off_drops_the_button_and_keeps_the_url(self):
        from engine.marketing.chart_render import render_chart_v2
        dates, o, h, lo, c, v = _sample_ohlcv()
        on = render_chart_v2("TEST", dates, o, h, lo, c, v, cta=True)
        off = render_chart_v2("TEST", dates, o, h, lo, c, v, cta=False)
        assert _BUTTON_LABEL in on and _BUTTON_GRADIENT in on
        assert _BUTTON_LABEL not in off, "trial button label survived cta=False"
        assert f'fill="url(#{_BUTTON_GRADIENT}' not in off, \
            "button gradient fill survived cta=False"
        assert _URL_LOCKUP in off, "the URL lockup must survive — only the pitch goes"
        assert "© 2026 Mastermind" in off

    def test_v2_card_off_is_still_valid_svg(self):
        from engine.marketing.chart_render import render_chart_v2
        dates, o, h, lo, c, v = _sample_ohlcv()
        off = render_chart_v2("TEST", dates, o, h, lo, c, v, cta=False)
        assert off.startswith("<svg") and off.rstrip().endswith("</svg>")

    def test_watchlist_card_honours_the_knob(self):
        from engine.marketing.chart_render import render_watchlist_card
        rows = [{"ticker": f"T{i}", "price": 10.0 + i, "pct_change": 1.0} for i in range(5)]
        on = render_watchlist_card("Theme", rows)
        off = render_watchlist_card("Theme", rows, cta=False)
        assert on == render_watchlist_card("Theme", rows, cta=True)
        assert _BUTTON_LABEL in on and _BUTTON_LABEL not in off
        assert _URL_LOCKUP in off

    def test_earnings_card_honours_the_knob(self):
        from engine.marketing.chart_render import render_earnings_card
        on = render_earnings_card("AAPL", "Apple Inc.", 2.10, 1.90, None, None)
        off = render_earnings_card("AAPL", "Apple Inc.", 2.10, 1.90, None, None, cta=False)
        assert on == render_earnings_card("AAPL", "Apple Inc.", 2.10, 1.90, None, None,
                                          cta=True)
        assert _BUTTON_LABEL in on and _BUTTON_LABEL not in off
        assert _URL_LOCKUP in off

    def test_breaking_card_honours_the_knob(self):
        from engine.marketing.chart_render import render_breaking_card
        kw = dict(headline="Fed holds rates steady", source_name="Federal Reserve",
                  source_tier="official", published_at="2026-07-27T18:00:00Z")
        on = render_breaking_card(**kw)
        off = render_breaking_card(**kw, cta=False)
        assert on == render_breaking_card(**kw, cta=True)
        assert _BUTTON_LABEL in on and _BUTTON_LABEL not in off
        assert _URL_LOCKUP in off

    def test_breaking_suppress_cta_still_removes_everything(self):
        """The per-item tragedy rule is unaffected by the account-wide knob."""
        from engine.marketing.chart_render import render_breaking_card
        kw = dict(headline="Heavy casualties reported", source_name="Reuters",
                  source_tier="wire", published_at="2026-07-27T18:00:00Z")
        for cta in (True, False):
            svg = render_breaking_card(**kw, suppress_cta=True, cta=cta)
            assert _BUTTON_LABEL not in svg
            assert _URL_LOCKUP not in svg


# ─────────────────────────────────────────────────────────────────────────────
# H. Send-time jitter
# ─────────────────────────────────────────────────────────────────────────────

class TestSendTimeJitter:

    def test_config_parses_strictly(self):
        from scripts.marketing_publisher import _jitter_max_cfg
        assert _jitter_max_cfg({}) == 0
        assert _jitter_max_cfg({"post_jitter_max_min": 0}) == 0
        assert _jitter_max_cfg({"post_jitter_max_min": -5}) == 0
        assert _jitter_max_cfg({"post_jitter_max_min": "nope"}) == 0
        assert _jitter_max_cfg({"post_jitter_max_min": 7}) == 7
        assert _jitter_max_cfg({"post_jitter_max_min": "7"}) == 7

    def test_live_config_sets_seven(self):
        """Pins the SHIPPED value — the in-code default is 0 (off), so without
        this assertion nothing records that jitter is actually armed. Change the
        number here in the same PR that changes it in config."""
        import yaml
        from pathlib import Path
        from scripts.marketing_publisher import _jitter_max_cfg
        cfg = yaml.safe_load(
            (Path(__file__).resolve().parent.parent / "config" / "marketing.yml")
            .read_text(encoding="utf-8"))
        assert _jitter_max_cfg(cfg["publish"]) == 7

    def test_offset_is_deterministic_for_a_fixed_id(self):
        from scripts.marketing_publisher import _post_jitter_minutes
        first = _post_jitter_minutes("ob-2026-07-27-flagship-abc123", 7)
        for _ in range(5):
            assert _post_jitter_minutes("ob-2026-07-27-flagship-abc123", 7) == first
        # And it is the crc32 residue, not an RNG draw.
        assert first == zlib.crc32(b"ob-2026-07-27-flagship-abc123") % 8

    def test_offset_is_bounded_by_the_config_max(self):
        from scripts.marketing_publisher import _post_jitter_minutes
        seen = set()
        for i in range(500):
            j = _post_jitter_minutes(f"item-{i}", 7)
            assert 0 <= j <= 7
            seen.add(j)
        # The whole range should be reachable, else the "break the exact-minute
        # pattern" premise is false.
        assert seen == set(range(8))

    def test_disabled_and_empty_id_give_zero(self):
        from scripts.marketing_publisher import _post_jitter_minutes
        assert _post_jitter_minutes("anything", 0) == 0
        assert _post_jitter_minutes("", 7) == 0

    def test_floor_seeds_from_the_booked_time_when_present(self, tmp_path):
        """A jittered post must not be followed inside its own floor window on
        the NEXT cron run — so the floor seeds from booked_at, not the row's at."""
        import json
        from scripts import marketing_publisher as mp

        ledger = tmp_path / "data" / "marketing" / "outbox"
        ledger.mkdir(parents=True)
        rows = [
            {"id": "old", "from": "posting", "to": "posted",
             "at": "2026-07-27T14:00:00Z", "actor": "publisher",
             "receipt": {"backend": "buffer", "at": "2026-07-27T14:00:00Z",
                         "booked_at": "2026-07-27T14:06:00Z"}},
        ]
        (ledger / "status_ledger.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

        got = mp._last_global_post_at(tmp_path)
        assert got == datetime(2026, 7, 27, 14, 6, tzinfo=timezone.utc)

    def test_floor_falls_back_to_at_for_pre_jitter_rows(self, tmp_path):
        import json
        from scripts import marketing_publisher as mp

        ledger = tmp_path / "data" / "marketing" / "outbox"
        ledger.mkdir(parents=True)
        (ledger / "status_ledger.jsonl").write_text(json.dumps(
            {"id": "old", "from": "posting", "to": "posted",
             "at": "2026-07-27T14:00:00Z", "actor": "publisher",
             "receipt": {"backend": "buffer", "at": "2026-07-27T14:00:00Z"}}
        ) + "\n", encoding="utf-8")
        assert mp._last_global_post_at(tmp_path) == \
            datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)

    def test_jitter_never_shortens_the_floor(self):
        """Jitter is ADDED to the floor-cleared time, so the gap between two
        consecutive BOOKED times is never less than the floor."""
        from scripts.marketing_publisher import _post_jitter_minutes, _within_floor

        floor_min, jitter_max = 10, 7
        booked_prev = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc) + \
            timedelta(minutes=_post_jitter_minutes("item-a", jitter_max))
        # The next sweep may only proceed once `now` clears the floor measured
        # from the previous BOOKED time; its own jitter only pushes it later.
        now = booked_prev
        while _within_floor(booked_prev, now, floor_min):
            now += timedelta(minutes=1)
        booked_next = now + timedelta(minutes=_post_jitter_minutes("item-b", jitter_max))
        assert (booked_next - booked_prev) >= timedelta(minutes=floor_min)

    def test_dry_run_report_books_the_jittered_minute(self, tmp_path, monkeypatch):
        """The admin preview must name the SAME minute the live run will book."""
        import json
        from scripts import marketing_publisher as mp

        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "marketing.yml").write_text(
            "publish:\n"
            "  backend: buffer\n"
            "  min_minutes_between_any_posts: 10\n"
            "  post_jitter_max_min: 7\n"
            "  channels:\n"
            "    flagship: chan-1\n",
            encoding="utf-8")
        obx = tmp_path / "data" / "marketing" / "outbox"
        obx.mkdir(parents=True)
        # crc32("it-jitter-4") % 8 == 7 — a PROVABLY NON-ZERO offset. The
        # original test used an id whose offset was 0, so it passed identically
        # with jitter disabled and proved nothing.
        item = {"id": _JITTER_ID, "account": "flagship", "kind": "signal",
                "text": "A perfectly ordinary post about the tape.",
                "scheduled_at": "2026-07-27T13:00:00Z", "status": "queued",
                "priority": 5, "as_of": "2026-07-27"}
        (obx / "items.jsonl").write_text(json.dumps(item) + "\n", encoding="utf-8")
        (obx / "status_ledger.jsonl").write_text(json.dumps(
            {"id": _JITTER_ID, "from": "queued", "to": "approved",
             "at": "2026-07-27T13:30:00Z", "actor": "operator"}) + "\n",
            encoding="utf-8")

        now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
        rep = mp.dry_run_report(tmp_path, now=now)
        assert rep["ok"], rep
        assert len(rep["would_post"]) == 1, rep
        assert _JITTER_OFFSET == 7, "fixture id no longer has the asserted offset"
        # The literal minute, not a re-derivation of the code under test.
        assert rep["would_post"][0]["send_at"] == "2026-07-27T14:07:00Z"
        assert rep["would_post"][0]["immediate"] is False
        # ...and it is NOT the un-jittered sweep minute.
        assert rep["would_post"][0]["send_at"] != now.strftime(mp._TS_FMT)

    def test_immediate_items_are_never_jittered(self, tmp_path):
        """Breaking cannot pay latency — an immediate item still books at now."""
        import json
        from scripts import marketing_publisher as mp

        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "marketing.yml").write_text(
            "publish:\n"
            "  backend: buffer\n"
            "  min_minutes_between_any_posts: 10\n"
            "  post_jitter_max_min: 7\n"
            "  channels:\n"
            "    flagship: chan-1\n",
            encoding="utf-8")
        obx = tmp_path / "data" / "marketing" / "outbox"
        obx.mkdir(parents=True)
        item = {"id": "it-immediate-1", "account": "flagship", "kind": "mover",
                "text": "Breaking: the tape just did something.",
                "scheduled_at": "immediate", "status": "queued",
                "priority": 5, "as_of": "2026-07-27"}
        (obx / "items.jsonl").write_text(json.dumps(item) + "\n", encoding="utf-8")
        (obx / "status_ledger.jsonl").write_text(json.dumps(
            {"id": "it-immediate-1", "from": "queued", "to": "approved",
             "at": "2026-07-27T13:30:00Z", "actor": "operator"}) + "\n",
            encoding="utf-8")

        now = datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
        rep = mp.dry_run_report(tmp_path, now=now)
        assert rep["ok"], rep
        assert rep["would_post"][0]["immediate"] is True
        assert rep["would_post"][0]["send_at"] == "2026-07-27T14:00:00Z"
        # Load-bearing: this id draws a 7-minute offset as a LADDER item, so the
        # assertion above would fail if the immediate path were jittered. The old
        # version asserted `>= 0`, which is true of every possible offset.
        assert mp._post_jitter_minutes("it-immediate-1", 7) == 7


# ─────────────────────────────────────────────────────────────────────────────
# F1. The per-account, tier-aware post-time cap
# ─────────────────────────────────────────────────────────────────────────────

class TestPerAccountEffectiveCap:
    """The plan gate cannot govern post time. An approved backlog — retries,
    operator approvals, items queued before the ramp shipped — has ALREADY
    cleared the gate, so the only thing standing between it and ~30 posts a day
    is the publisher's own cap check, which read the unlimited base value."""

    def test_stricter_daily_cap_dialects(self):
        from engine.marketing.outbox import stricter_daily_cap
        # base unlimited (-1) + tier bounded -> the tier
        assert stricter_daily_cap(-1, 2) == 2
        # base bounded + tier unlimited (None) -> the base
        assert stricter_daily_cap(3, None) == 3
        # both unlimited stays unlimited
        assert stricter_daily_cap(-1, None) == -1
        # both bounded -> the smaller, from either side
        assert stricter_daily_cap(5, 2) == 2
        assert stricter_daily_cap(1, 4) == 1
        assert stricter_daily_cap(-1, 0) == 0

    def test_week_one_account_is_capped_at_its_tier_not_unlimited(self):
        from engine.marketing.outbox import effective_cap, effective_cap_for
        cfg = _cfg(accounts=[_acct("cold", created=_minus(3))], ramp=_RAMP_TABLE)
        assert effective_cap(cfg) == -1              # the base is unlimited...
        assert effective_cap_for(cfg, "cold", _AS_OF) == 2   # ...the desk is not

    def test_graduated_account_keeps_the_unlimited_base(self):
        from engine.marketing.outbox import effective_cap_for
        cfg = _cfg(accounts=[_acct("warm", created=_minus(200))], ramp=_RAMP_TABLE)
        assert effective_cap_for(cfg, "warm", _AS_OF) == -1

    def test_outbox_ceiling_still_lowers_a_tier_cap(self):
        from engine.marketing.outbox import effective_cap_for
        cfg = _cfg(accounts=[_acct("cold", created=_minus(3))], ramp=_RAMP_TABLE)
        cfg["outbox"] = {"max_posts_per_account_per_day": 1}
        assert effective_cap_for(cfg, "cold", _AS_OF) == 1

    def test_unknown_account_falls_closed_to_the_strictest_tier(self):
        from engine.marketing.outbox import effective_cap_for
        cfg = _cfg(accounts=[_acct("known", created=_minus(200))], ramp=_RAMP_TABLE)
        assert effective_cap_for(cfg, "ghost", _AS_OF) == 2

    def test_no_ramp_table_is_a_no_op(self):
        from engine.marketing.outbox import effective_cap, effective_cap_for
        cfg = _cfg(accounts=[_acct("cold", created=_minus(1))])
        assert effective_cap_for(cfg, "cold", _AS_OF) == effective_cap(cfg) == -1


_PUB_CFG_YAML = (
    "sentinel:\n"
    "  max_posts_per_account_per_day: -1\n"
    "  ramp:\n"
    "    graduate_after_days: 56\n"
    "    weeks_1_2:\n"
    "      max_posts_per_account_per_day: 2\n"
    "publish:\n"
    "  backend: buffer\n"
    "  min_minutes_between_any_posts: 0\n"
    "  channels:\n"
    "    flagship: chan-1\n"
    "desk_network:\n"
    "  accounts:\n"
    "    - id: flagship\n"
    "      enabled: true\n"
    "      created: \"{created}\"\n"
)


def _backlog_tree(tmp_path, created: str) -> None:
    """Two posts already out today + a third approved and due, on one account."""
    import json
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "marketing.yml").write_text(
        _PUB_CFG_YAML.format(created=created), encoding="utf-8")
    obx = tmp_path / "data" / "marketing" / "outbox"
    obx.mkdir(parents=True)

    items, ledger = [], []
    for n in range(2):
        iid = f"done-{n}"
        items.append({"id": iid, "account": "flagship", "kind": "signal",
                      "text": f"Post number {n} about the tape today.",
                      "scheduled_at": "2026-07-27T12:00:00Z",
                      "status": "queued", "priority": 5, "as_of": "2026-07-27"})
        ledger += [
            {"id": iid, "from": "queued", "to": "approved",
             "at": "2026-07-27T12:00:00Z", "actor": "operator"},
            {"id": iid, "from": "approved", "to": "posting",
             "at": "2026-07-27T12:01:00Z", "actor": "publisher"},
            {"id": iid, "from": "posting", "to": "posted",
             "at": "2026-07-27T12:02:00Z", "actor": "publisher"},
        ]
    items.append({"id": "third", "account": "flagship", "kind": "signal",
                  "text": "A third, entirely different post for today.",
                  "scheduled_at": "2026-07-27T13:00:00Z",
                  "status": "queued", "priority": 5, "as_of": "2026-07-27"})
    ledger.append({"id": "third", "from": "queued", "to": "approved",
                   "at": "2026-07-27T13:30:00Z", "actor": "operator"})
    (obx / "items.jsonl").write_text(
        "".join(json.dumps(i) + "\n" for i in items), encoding="utf-8")
    (obx / "status_ledger.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in ledger), encoding="utf-8")


class TestPublisherCapIsRampAware:

    def test_week_one_backlog_is_held_at_the_tier_cap(self, tmp_path):
        """END TO END on the defect: base cap -1, two posts already out today, a
        third approved and due. Before the fix `_at_cap(2, -1)` was False and the
        third went out — and the next sweep took the fourth."""
        from scripts import marketing_publisher as mp
        _backlog_tree(tmp_path, "2026-07-25")           # 2 days old → weeks_1_2
        rep = mp.dry_run_report(
            tmp_path, now=datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc))
        assert rep["ok"], rep
        assert rep["cap"] == -1, "the BASE cap is still unlimited"
        assert rep["counts"]["skipped_cap"] == 1, rep
        assert rep["would_post"] == [], rep

    def test_graduated_backlog_still_drains(self, tmp_path):
        """The mirror image: the same backlog on a warm desk is NOT capped."""
        from scripts import marketing_publisher as mp
        _backlog_tree(tmp_path, "2025-01-01")           # graduated
        rep = mp.dry_run_report(
            tmp_path, now=datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc))
        assert rep["ok"], rep
        assert rep["counts"]["skipped_cap"] == 0, rep
        assert len(rep["would_post"]) == 1, rep

    def test_admin_outbox_exposes_the_per_account_caps(self, tmp_path):
        """The scalar `cap` stays the base ceiling (frozen contract); the honest
        per-desk number rides alongside it."""
        import admin.marketing as am
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "marketing.yml").write_text(
            "sentinel:\n"
            "  max_posts_per_account_per_day: -1\n"
            "  ramp:\n"
            "    graduate_after_days: 56\n"
            "    weeks_1_2:\n"
            "      max_posts_per_account_per_day: 2\n"
            "publish:\n"
            "  backend: buffer\n"
            "desk_network:\n"
            "  accounts:\n"
            "    - id: cold\n"
            "      enabled: true\n"
            "      created: \"2026-07-25\"\n"
            "    - id: warm\n"
            "      enabled: true\n"
            "      created: \"2025-01-01\"\n",
            encoding="utf-8")
        (tmp_path / "data" / "marketing" / "outbox").mkdir(parents=True)

        obx = am.outbox(tmp_path)
        assert obx["ok"], obx
        assert obx["cap"] == -1
        assert obx["caps_by_account"] == {"cold": 2, "warm": -1}, obx["caps_by_account"]


# ─────────────────────────────────────────────────────────────────────────────
# F2. The publish-time lane was DEAD at the live cap
# ─────────────────────────────────────────────────────────────────────────────

class TestPublishTimeLaneRevival:
    """`posted_today.get(aid, 0) >= cap` with the live unlimited cap of -1 is
    `0 >= -1` — True for every account, every run. The auto-approved mover/theme
    lane therefore generated NOTHING from 2026-07-24 onward. The existing suite
    only ever passed cap=2, which is why it survived."""

    @pytest.fixture(autouse=True)
    def _stub_publish_time_card(self, monkeypatch):
        """The publish-time lane now refuses to enqueue a mover/theme item whose
        card cannot be hosted (2026-07-31). These tests are about the RAMP tiers,
        run under tmp_path with no renderer and no R2, so the card is stubbed to
        its happy path and the tier assertions keep measuring the tier."""
        from engine.marketing import publish_time_content as _ptc

        # Keyword-pinned, mirroring the autouse stub in
        # test_marketing_publish_time_content.py: a `lambda cand, **kw` absorbs
        # any signature, so a change to _resolve_card's call contract would be
        # caught in one file and silently swallowed here, leaving the ramp-tier
        # assertions passing against a lane that can no longer resolve a card.
        def _stub_card(cand, *, root, cfg, as_of, now, slot):
            return {
                "media": {"kind": "chart_svg", "chart_id": "stub",
                          "path": "data/marketing/outbox/media/stub.svg",
                          "media_url": "https://cards.example/stub.png"},
                "published": {"chart_id": "stub"}, "reason": "ok"}

        monkeypatch.setattr(_ptc, "_resolve_card", _stub_card)

    def test_unlimited_cap_does_not_block_every_account(self, tmp_path):
        """THE REGRESSION: at cap=-1 the lane must still generate."""
        from engine.marketing import outbox, publish_time_content as ptc
        TestPublishTimeLaneRamp._write_fixtures(tmp_path)
        report = ptc.generate_slot_items(
            tmp_path, cfg=TestPublishTimeLaneRamp._pt_cfg(_minus(200, _AS_OF)),
            now=TestPublishTimeLaneRamp.NOW, state=outbox.fold_state(tmp_path),
            approved_due=[], posted_counts={}, cap=-1, live=True,
        )
        assert report.get("generated"), report
        assert [i for i in outbox.read_items(tmp_path) if i["kind"] == "theme_list"]
        assert "no_account" not in {d["reason"] for d in report.get("dropped", [])}

    @staticmethod
    def _prefill(tmp_path, n_posted: int) -> None:
        """n already-POSTED items on `flagship` today."""
        import json
        obx = tmp_path / "data" / "marketing" / "outbox"
        obx.mkdir(parents=True, exist_ok=True)
        today = TestPublishTimeLaneRamp.NOW.strftime("%Y-%m-%d")
        rows, items = [], []
        for n in range(n_posted):
            iid = f"pt-done-{n}"
            items.append({"id": iid, "account": "flagship", "kind": "mover",
                          "text": f"Earlier post number {n} about the tape.",
                          "scheduled_at": "immediate", "status": "queued",
                          "priority": 6, "as_of": today})
            rows += [
                {"id": iid, "from": "queued", "to": "approved",
                 "at": f"{today}T13:00:00Z", "actor": "operator"},
                {"id": iid, "from": "approved", "to": "posting",
                 "at": f"{today}T13:01:00Z", "actor": "publisher"},
                {"id": iid, "from": "posting", "to": "posted",
                 "at": f"{today}T13:02:00Z", "actor": "publisher"},
            ]
        (obx / "items.jsonl").write_text(
            "".join(json.dumps(i) + "\n" for i in items), encoding="utf-8")
        (obx / "status_ledger.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    @pytest.mark.parametrize("posted,expect_generation", [(3, True), (4, False)])
    def test_unlimited_cap_is_still_narrowed_by_the_tier(
            self, tmp_path, posted, expect_generation):
        """A desk at cap=-1 gets its TIER's ceiling, not no ceiling at all.

        week_5_plus allows 4/day and allows theme_list, so ONLY the cap can bite.
        BOTH halves matter: at 3 posted the lane must still generate (that half
        fails on the pre-fix tree, where -1 blocked everything), and at 4 it must
        stop (that half is the new tier bound).
        """
        from engine.marketing import outbox, publish_time_content as ptc
        TestPublishTimeLaneRamp._write_fixtures(tmp_path)
        self._prefill(tmp_path, posted)

        report = ptc.generate_slot_items(
            tmp_path, cfg=TestPublishTimeLaneRamp._pt_cfg(_minus(30, _AS_OF)),
            now=TestPublishTimeLaneRamp.NOW, state=outbox.fold_state(tmp_path),
            approved_due=[], posted_counts={}, cap=-1, live=True,
        )
        if expect_generation:
            assert report.get("generated"), report
        else:
            assert not report.get("generated"), report
            assert "no_account" in {d["reason"] for d in report.get("dropped", [])}


# ─────────────────────────────────────────────────────────────────────────────
# F3. A typo in a tier row must not silently flip the whole gate
# ─────────────────────────────────────────────────────────────────────────────

class TestTierValueParseFailure:

    def _caps(self, tier_row: dict) -> dict:
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("a", created=_minus(1))],
                   ramp={"graduate_after_days": 56, "weeks_1_2": tier_row})
        return resolve_ramp(cfg, _AS_OF)["accounts"]["a"]["caps"]

    def test_unparseable_unlimited_cap_does_not_become_minus_one(self, capsys):
        """THE 100%-QUARANTINE BUG: the -1 fallback was stored as a BOUNDED cap,
        so `posts_count >= -1` was true for every item in the plan."""
        caps = self._caps({"max_posts_per_account_per_day": "two"})
        assert caps["max_posts_per_account_per_day"] is None, \
            "a typo must leave the base (unlimited) in place, never -1"
        out = capsys.readouterr().out
        hits = [ln for ln in out.splitlines()
                if "sentinel-ramp-tier-value-unparseable" in ln]
        assert hits and hits[0].startswith("::"), out
        assert "weeks_1_2" in hits[0] and "max_posts_per_account_per_day" in hits[0]

    def test_unparseable_bounded_cap_keeps_base_and_warns(self, capsys):
        """The opposite silent failure: this branch fell back to the LOOSER base
        without a word. Same answer now, but out loud."""
        caps = self._caps({"max_cashtags_per_post": "two"})
        assert caps["max_cashtags_per_post"] == 3      # the base value
        out = capsys.readouterr().out
        assert "sentinel-ramp-tier-value-unparseable" in out
        assert any(ln.startswith("::") for ln in out.splitlines())

    def test_present_null_is_treated_as_a_typo(self, capsys):
        caps = self._caps({"max_posts_per_account_per_day": None})
        assert caps["max_posts_per_account_per_day"] is None
        assert "sentinel-ramp-tier-value-unparseable" in capsys.readouterr().out

    def test_a_full_plan_is_not_quarantined_by_the_typo(self):
        """The user-visible consequence, end to end."""
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("a", created=_minus(1))],
                   ramp={"graduate_after_days": 56,
                         "weeks_1_2": {"max_posts_per_account_per_day": "two"}})
        plan = _plan({"a": [_item("i1", cashtag="$AAA", slot="D1-a"),
                            _item("i2", cashtag="$BBB", slot="D1-b")]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert report["counts"]["quarantined"] == 0, report["quarantined"]

    def test_a_valid_tier_row_emits_no_warning(self, capsys):
        caps = self._caps({"max_posts_per_account_per_day": 2})
        assert caps["max_posts_per_account_per_day"] == 2
        assert "unparseable" not in capsys.readouterr().out

    def test_unlimited_string_is_valid_not_a_typo(self, capsys):
        caps = self._caps({"max_posts_per_account_per_day": "unlimited"})
        assert caps["max_posts_per_account_per_day"] is None
        assert "unparseable" not in capsys.readouterr().out


# ─────────────────────────────────────────────────────────────────────────────
# F4. A missing as_of degrades the WHOLE network — say so
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingAsOfAnnotation:

    def test_old_account_with_no_as_of_falls_closed_and_warns(self, capsys):
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("ancient", created="2020-01-01")], ramp=_RAMP_TABLE)
        ramp = resolve_ramp(cfg, "")
        assert ramp["as_of_usable"] is False
        assert ramp["accounts"]["ancient"]["tier"] == "weeks_1_2", \
            "a 6-year-old account must still fail CLOSED without a reference date"
        assert ramp["accounts"]["ancient"]["caps"]["max_posts_per_account_per_day"] == 2
        out = capsys.readouterr().out
        hits = [ln for ln in out.splitlines() if "sentinel-ramp-as-of-missing" in ln]
        assert hits, out
        assert hits[0].startswith("::")

    def test_unparseable_as_of_warns_too(self, capsys):
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("ancient", created="2020-01-01")], ramp=_RAMP_TABLE)
        assert resolve_ramp(cfg, "not-a-date")["as_of_usable"] is False
        assert "sentinel-ramp-as-of-missing" in capsys.readouterr().out

    def test_usable_as_of_emits_nothing(self, capsys):
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("ancient", created="2020-01-01")], ramp=_RAMP_TABLE)
        assert resolve_ramp(cfg, _AS_OF)["as_of_usable"] is True
        assert "sentinel-ramp-as-of-missing" not in capsys.readouterr().out

    def test_gate_report_carries_the_note(self, capsys):
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("ancient", created="2020-01-01")], ramp=_RAMP_TABLE)
        plan = _plan({"ancient": [_item("i1")]}, as_of="")
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert report["checks"]["ramp"]["as_of_usable"] is False
        assert any("as_of" in n and "network-wide" in n for n in report["notes"]), \
            report["notes"]
        assert "sentinel-ramp-as-of-missing" in capsys.readouterr().out

    def test_no_ramp_table_stays_silent(self, capsys):
        """Nothing is enforced, so nothing degraded — no warning."""
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("ancient", created="2020-01-01")])
        resolve_ramp(cfg, "")
        assert "sentinel-ramp-as-of-missing" not in capsys.readouterr().out


# ─────────────────────────────────────────────────────────────────────────────
# N7 / N8 / N10 — the nits, each with a live consequence
# ─────────────────────────────────────────────────────────────────────────────

class TestRampNits:

    def test_graduate_after_days_is_clamped_to_the_week_3_4_boundary(self):
        """Below 28 the knob is inert: the age<14 / age<28 branches fire first.
        Clamping makes it mean what it says at every value."""
        from engine.marketing.sentinel import (
            effective_graduate_after_days, resolve_ramp_tier)
        assert effective_graduate_after_days(56) == 56
        assert effective_graduate_after_days(20) == 28
        assert effective_graduate_after_days(0) == 28
        assert effective_graduate_after_days("junk") == 56    # in-code default
        # A 30-day account under a configured-20 ramp: inert before, graduated now.
        assert resolve_ramp_tier(_minus(30), _AS_OF, graduate_after_days=20) == "graduated"

    def test_clamped_value_is_reported(self):
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("a", created=_minus(1))],
                   ramp={**_RAMP_TABLE, "graduate_after_days": 5})
        assert resolve_ramp(cfg, _AS_OF)["graduate_after_days"] == 28

    def test_theme_list_allowed_is_readable_from_the_base_block(self):
        """N8: it was the one base knob hardcoded in Python."""
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("warm", created=_minus(200))], ramp=_RAMP_TABLE,
                   base_overrides={"theme_list_allowed": False})
        caps = resolve_ramp(cfg, _AS_OF)["accounts"]["warm"]["caps"]
        assert caps["theme_list_allowed"] is False, \
            "a graduated desk must still honour a base-block theme_list ban"

    def test_base_theme_list_ban_quarantines_on_a_graduated_account(self):
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg(accounts=[_acct("warm", created=_minus(200))], ramp=_RAMP_TABLE,
                   base_overrides={"theme_list_allowed": False})
        plan = _plan({"warm": [_item("t1", type="theme_list", slot="D1-t",
                                     body="$AAA $BBB $CCC $DDD moved together.")]})
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1, graded_window=[])
        assert "ramp_theme_list" in _reasons(report, "t1")

    def test_theme_list_default_is_still_allowed(self):
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("warm", created=_minus(200))], ramp=_RAMP_TABLE)
        caps = resolve_ramp(cfg, _AS_OF)["accounts"]["warm"]["caps"]
        assert caps["theme_list_allowed"] is True

    def test_each_annotation_prints_once_per_process(self, capsys):
        """N10: resolve_ramp runs several times per publisher sweep (the gate, the
        cap resolver, the publish-time lane). A config defect does not become
        more true by being printed six times."""
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("nodate")], ramp=_RAMP_TABLE)
        for _ in range(5):
            resolve_ramp(cfg, _AS_OF)
        out = capsys.readouterr().out
        assert out.count("sentinel-ramp-created-missing") == 1, out

    def test_reset_makes_the_annotation_available_again(self, capsys):
        from engine.marketing.sentinel import resolve_ramp, reset_ramp_announcements
        cfg = _cfg(accounts=[_acct("nodate")], ramp=_RAMP_TABLE)
        resolve_ramp(cfg, _AS_OF)
        capsys.readouterr()
        reset_ramp_announcements()
        resolve_ramp(cfg, _AS_OF)
        assert "sentinel-ramp-created-missing" in capsys.readouterr().out

    def test_announce_false_never_prints_even_when_fresh(self, capsys):
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("nodate")], ramp=_RAMP_TABLE)
        resolve_ramp(cfg, "", announce=False)
        assert capsys.readouterr().out == ""

    def test_distinct_accounts_each_get_their_own_warning(self, capsys):
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg(accounts=[_acct("a1"), _acct("a2")], ramp=_RAMP_TABLE)
        resolve_ramp(cfg, _AS_OF)
        out = capsys.readouterr().out
        assert out.count("sentinel-ramp-created-missing") == 2, out


# ─────────────────────────────────────────────────────────────────────────────
# F5. main()'s booking path — the thing dry_run_report only projects
# ─────────────────────────────────────────────────────────────────────────────

class TestMainBookingPath:
    """dry_run_report mirrors main(), but a mirror is not the original: nothing
    covered the dueAt actually handed to Buffer, or the receipt's booked_at."""

    @staticmethod
    def _tree(tmp_path, item_id: str, scheduled_at: str) -> None:
        import json
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "marketing.yml").write_text(
            "sentinel:\n"
            "  max_posts_per_account_per_day: -1\n"
            "publish:\n"
            "  backend: buffer\n"
            "  min_minutes_between_any_posts: 10\n"
            "  post_jitter_max_min: 7\n"
            "  channels:\n"
            "    flagship: chan-1\n"
            "desk_network:\n"
            "  accounts:\n"
            "    - id: flagship\n"
            "      enabled: true\n"
            "      created: \"2025-01-01\"\n",
            encoding="utf-8")
        obx = tmp_path / "data" / "marketing" / "outbox"
        obx.mkdir(parents=True)
        (obx / "items.jsonl").write_text(json.dumps(
            {"id": item_id, "account": "flagship", "kind": "signal",
             "text": "A perfectly ordinary post about the tape.",
             "scheduled_at": scheduled_at, "status": "queued",
             "priority": 5, "as_of": "2026-07-27"}) + "\n", encoding="utf-8")
        (obx / "status_ledger.jsonl").write_text(json.dumps(
            {"id": item_id, "from": "queued", "to": "approved",
             "at": "2026-07-27T13:30:00Z", "actor": "operator"}) + "\n",
            encoding="utf-8")

    def _run_live(self, tmp_path, monkeypatch, item_id, scheduled_at) -> dict:
        """Drive main() --live with the network and the tape gate stubbed out.
        Returns the kwargs the backend publisher was called with."""
        from scripts import marketing_publisher as mp
        from engine.marketing import live_verify as lv
        from engine.marketing import social_publisher as sp

        self._tree(tmp_path, item_id, scheduled_at)
        captured: dict = {}

        class _FakeReceipt:
            ok = True
            backend = "buffer"
            external_id = "ext-1"
            external_url = "https://x.com/p/1"
            error = None
            at = "2026-07-27T14:07:03Z"

        class _FakePublisher:
            def publish(self, **kwargs):
                captured.update(kwargs)
                # Resolve the dueAt exactly as the real adapter would, so the
                # 3-minute Buffer lead is part of what this test observes.
                captured["due_at"] = sp._effective_due_at(
                    kwargs.get("scheduled_at"), kwargs.get("now"),
                    immediate=kwargs.get("immediate", False))
                return _FakeReceipt()

        monkeypatch.setattr(mp, "_make_publisher", lambda *a, **k: _FakePublisher())
        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
        monkeypatch.setenv("BUFFER_TOKEN", "tok")
        # The live tape gate reads repo data this tmp tree does not have.
        monkeypatch.setattr(lv, "verify_item",
                            lambda *a, **k: {"action": "post", "reasons": []})

        rc = mp.main(["--live", "--root", str(tmp_path),
                      "--now", "2026-07-27T14:00:00Z"])
        assert rc == 0, rc
        assert captured, "the publisher was never called — nothing posted"
        return captured

    def test_ladder_item_books_now_plus_its_jitter(self, tmp_path, monkeypatch):
        captured = self._run_live(tmp_path, monkeypatch, _JITTER_ID,
                                  "2026-07-27T13:00:00Z")
        assert _JITTER_OFFSET == 7
        # main() hands Buffer the BOOKED wall-clock, not the item's stale slot.
        assert captured["scheduled_at"] == "2026-07-27T14:07:00Z"
        assert captured["immediate"] is False
        # And the adapter honours it: max(now+3min lead, booked) == booked here.
        assert captured["due_at"] == "2026-07-27T14:07:00Z"

    def test_receipt_records_the_booked_time(self, tmp_path, monkeypatch):
        """_last_global_post_at seeds the NEXT cron run's floor from this field —
        without it a jittered post could be followed 3 minutes later."""
        from engine.marketing import outbox
        from scripts import marketing_publisher as mp
        self._run_live(tmp_path, monkeypatch, _JITTER_ID, "2026-07-27T13:00:00Z")
        rows = [r for r in outbox.read_ledger(tmp_path) if r.get("to") == "posted"]
        assert len(rows) == 1, rows
        assert rows[0]["receipt"]["booked_at"] == "2026-07-27T14:07:00Z"
        # ...and the floor reads it back.
        assert mp._last_global_post_at(tmp_path) == datetime(
            2026, 7, 27, 14, 7, tzinfo=timezone.utc)

    def test_short_offset_lands_on_the_buffer_lead_not_its_own_minute(
            self, tmp_path, monkeypatch):
        """The distribution is NOT uniform: offsets 0-3 all deliver at now+3."""
        from scripts import marketing_publisher as mp
        assert mp._post_jitter_minutes("it-jitter-2", 7) == 2
        captured = self._run_live(tmp_path, monkeypatch, "it-jitter-2",
                                  "2026-07-27T13:00:00Z")
        assert captured["scheduled_at"] == "2026-07-27T14:02:00Z"   # what we book
        assert captured["due_at"] == "2026-07-27T14:03:00Z"         # what ships

    def test_immediate_item_books_now_and_shares_now(self, tmp_path, monkeypatch):
        captured = self._run_live(tmp_path, monkeypatch, "it-immediate-1", "immediate")
        assert captured["immediate"] is True
        assert captured["scheduled_at"] == "2026-07-27T14:00:00Z"
        assert captured["due_at"] == "2026-07-27T14:03:00Z"   # share-now + lead

    def test_delivered_offsets_collapse_onto_the_lead(self):
        """The honest shape the config comment now states: at max 7 the delivered
        offsets are {3,3,3,3,4,5,6,7} — half the mass on the lead minute."""
        from scripts.marketing_publisher import _post_jitter_minutes
        delivered = [max(3, _post_jitter_minutes(f"x{i}", 7)) for i in range(4000)]
        assert set(delivered) == {3, 4, 5, 6, 7}
        # 0,1,2,3 out of 0..7 all deliver at 3 → about half of everything.
        share_at_lead = delivered.count(3) / len(delivered)
        assert 0.4 < share_at_lead < 0.6, share_at_lead
