"""tests/test_marketing_ramp_speedup.py — the D08 age ramp is an OPERATOR LEVER.

WHAT WENT WRONG (operator, 2026-08-03): "uhhh she should be posting. relax the
account age thingy and speed up its ramp up for new accs added."

Kelly's desk was created 2026-07-28 and had never posted once, ever. Her one and
only planned at-bat was a `theme_list`, which `sentinel.ramp.weeks_1_2.
theme_list_allowed: false` killed at plan-build (masterplan §8.1 V2). Relaxing
the schedule was not a config edit, though: the two tier boundaries were MODULE
CONSTANTS (`_RAMP_WEEKS_1_2_MAX_DAYS = 14`, `_RAMP_WEEKS_3_4_MAX_DAYS = 28`), and
`effective_graduate_after_days` clamped `graduate_after_days` up to the hardcoded
28 — so every configured graduation under 28 was silently INERT. A "we sped the
ramp up" config edit would have read as applied while every desk stayed on the
old schedule.

WHAT THIS SUITE PINS.

  1. The two boundaries are config-readable (`sentinel.ramp.weeks_1_2_days` /
     `weeks_3_4_days`) and actually move the tier a given age resolves to.
  2. On the SHIPPED config a 5-day-old desk is `weeks_3_4` (it was `weeks_1_2`)
     and a 10-day-old desk is `week_5_plus` (it was `weeks_1_2`).
  3. `graduate_after_days: 21` graduates at 21, not at the old clamp floor of 28.
  4. An INCOHERENT pair reverts BOTH boundaries to the code defaults and says so
     with a bare line-start `::warning` — asserted with capsys and
     `line.startswith("::")`, because a logger would prefix the line and GitHub
     would drop it (tests/test_gh_annotation_line_start.py).
  5. A config that names NEITHER key behaves byte-identically to the pre-2026-08-03
     14/28 schedule — the whole relaxation must be opt-in.
  6. Kelly can post, and `theme_list` is no longer banned for her at any age.

WHAT THIS SUITE IS NOT. The ramp is a PLATFORM-RISK throttle (a days-old account
must not post like a spambot), not a content-quality gate. Nothing here asserts
anything about `salience_threshold`, the near-dup Jaccard, the number budget, the
payload gate, tape freshness or the approval desk — those are the quality gates,
they live elsewhere, and the relaxation did not touch them.

DETERMINISM. `resolve_ramp_tier` takes `created`/`as_of` from plan inputs and must
never read a wall clock, so every age below is expressed as an OFFSET from a
fixed date. No test here reads `date.today()`.

CONVENTIONS. Reads the committed config only; no network, no writes.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

#: The shipped fast schedule (config/marketing.yml sentinel.ramp, 2026-08-03).
SHIPPED_WEEKS_1_2_DAYS = 5
SHIPPED_WEEKS_3_4_DAYS = 10
SHIPPED_GRADUATE_AFTER_DAYS = 21

#: The pre-relaxation code defaults, which an absent config must still produce.
LEGACY_WEEKS_1_2_DAYS = 14
LEGACY_WEEKS_3_4_DAYS = 28

_AS_OF = "2026-08-03"        # the day of the operator order


@pytest.fixture(autouse=True)
def _fresh_annotations():
    """sentinel emits each ramp ``::warning`` at most once per PROCESS. Under
    pytest the whole file is one process, so without this reset the first test to
    trip a warning would silence every later test asserting on the same one."""
    from engine.marketing.sentinel import reset_ramp_announcements
    reset_ramp_announcements()
    yield
    reset_ramp_announcements()


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


def _minus(days: int, *, as_of: str = _AS_OF) -> str:
    """The created: date that makes an account exactly ``days`` old at as_of."""
    return (date.fromisoformat(as_of) - timedelta(days=days)).isoformat()


def _tier_row(*, weeks_1_2_days: Any = None, weeks_3_4_days: Any = None,
              graduate_after_days: int = SHIPPED_GRADUATE_AFTER_DAYS) -> dict:
    """A minimal but REAL ramp table — three tier rows, so `enforced` is True."""
    ramp: dict[str, Any] = {
        "graduate_after_days": graduate_after_days,
        "weeks_1_2": {"max_posts_per_account_per_day": 14,
                      "theme_list_allowed": True},
        "weeks_3_4": {"max_posts_per_account_per_day": 18,
                      "theme_list_allowed": True},
        "week_5_plus": {"max_posts_per_account_per_day": 20,
                        "theme_list_allowed": True},
    }
    if weeks_1_2_days is not None:
        ramp["weeks_1_2_days"] = weeks_1_2_days
    if weeks_3_4_days is not None:
        ramp["weeks_3_4_days"] = weeks_3_4_days
    return ramp


def _cfg_with(ramp: dict, *, created: str) -> dict:
    return {
        "sentinel": {
            "max_posts_per_account_per_day": -1,
            "max_media_posts_per_account_per_day": -1,
            "max_cashtags_per_post": 3,
            "links_allowed": False,
            "ramp": ramp,
        },
        "desk_network": {"stage": "A", "accounts": [
            {"id": "newdesk", "kind": "branded", "voice": "desk",
             "enabled": True, "created": created},
        ]},
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. The boundaries are config-readable and they MOVE the tier
# ─────────────────────────────────────────────────────────────────────────────

class TestBoundariesAreConfigurable:

    def test_resolve_ramp_boundaries_reads_both_keys(self):
        from engine.marketing.sentinel import resolve_ramp_boundaries
        assert resolve_ramp_boundaries({"weeks_1_2_days": 5,
                                        "weeks_3_4_days": 10}) == (5, 10)

    def test_absent_keys_are_the_legacy_schedule(self):
        """The whole relaxation is opt-in: no keys ⇒ the pre-2026-08-03 14/28."""
        from engine.marketing.sentinel import resolve_ramp_boundaries
        assert resolve_ramp_boundaries({}) == (LEGACY_WEEKS_1_2_DAYS,
                                               LEGACY_WEEKS_3_4_DAYS)
        assert resolve_ramp_boundaries(None) == (LEGACY_WEEKS_1_2_DAYS,
                                                 LEGACY_WEEKS_3_4_DAYS)

    @pytest.mark.parametrize("raw", [None, "", "five", [], {}, True, False])
    def test_junk_values_fall_back_to_the_defaults(self, raw):
        """This block is an operator lever, never a load-bearing dependency —
        junk must degrade to the shipped schedule, not raise. ``True`` is in the
        list on purpose: ``int(True) == 1`` would otherwise read a stray
        ``weeks_1_2_days: true`` as a ONE-DAY first tier."""
        from engine.marketing.sentinel import resolve_ramp_boundaries
        assert resolve_ramp_boundaries({"weeks_1_2_days": raw}) == (
            LEGACY_WEEKS_1_2_DAYS, LEGACY_WEEKS_3_4_DAYS)

    def test_a_numeric_value_truncates_like_every_other_cap_knob(self):
        """Same coercion contract as sentinel._cap: a number is a number. Pinned
        so the behaviour is a decision rather than an accident — 3.7 days is a
        3-day first tier, not a fallback to 14."""
        from engine.marketing.sentinel import resolve_ramp_boundaries
        assert resolve_ramp_boundaries({"weeks_1_2_days": 3.7,
                                        "weeks_3_4_days": "10"}) == (3, 10)

    @pytest.mark.parametrize("age,tier", [
        (0, "weeks_1_2"),
        (4, "weeks_1_2"),       # boundary: last day of tier 1 at 5/10
        (5, "weeks_3_4"),       # boundary: first day of tier 2 — was weeks_1_2
        (9, "weeks_3_4"),       # boundary: last day of tier 2
        (10, "week_5_plus"),    # boundary: first day of tier 3 — was weeks_1_2
        (20, "week_5_plus"),    # boundary: last ramped day at graduate 21
        (21, "graduated"),      # boundary: graduate_after_days
    ])
    def test_the_fast_ladder_is_walked_from_both_sides(self, age, tier):
        from engine.marketing.sentinel import resolve_ramp_tier
        assert resolve_ramp_tier(
            _minus(age), _AS_OF,
            graduate_after_days=SHIPPED_GRADUATE_AFTER_DAYS,
            weeks_1_2_days=SHIPPED_WEEKS_1_2_DAYS,
            weeks_3_4_days=SHIPPED_WEEKS_3_4_DAYS) == tier

    @pytest.mark.parametrize("age,tier", [
        (0, "weeks_1_2"),
        (13, "weeks_1_2"),
        (14, "weeks_3_4"),
        (27, "weeks_3_4"),
        (28, "week_5_plus"),
        (55, "week_5_plus"),
        (56, "graduated"),
    ])
    def test_the_legacy_ladder_is_reproduced_when_nothing_is_configured(
            self, age, tier):
        """The mutation-sensitive half of "opt-in": with no boundary arguments the
        function must still produce the exact 14/28/56 table it shipped with."""
        from engine.marketing.sentinel import resolve_ramp_tier
        assert resolve_ramp_tier(_minus(age), _AS_OF) == tier

    @pytest.mark.parametrize("created", [None, "", "not-a-date", "2026-13-45"])
    def test_a_fast_schedule_still_fails_closed_on_an_unusable_created(
            self, created):
        """Speeding the ramp up must not change WHICH tier corrupt data lands on:
        still weeks_1_2, the strictest."""
        from engine.marketing.sentinel import resolve_ramp_tier
        assert resolve_ramp_tier(
            created, _AS_OF, weeks_1_2_days=SHIPPED_WEEKS_1_2_DAYS,
            weeks_3_4_days=SHIPPED_WEEKS_3_4_DAYS) == "weeks_1_2"

    def test_a_future_created_still_fails_closed(self):
        from engine.marketing.sentinel import resolve_ramp_tier
        assert resolve_ramp_tier(
            "2027-01-01", _AS_OF, weeks_1_2_days=SHIPPED_WEEKS_1_2_DAYS,
            weeks_3_4_days=SHIPPED_WEEKS_3_4_DAYS) == "weeks_1_2"

    def test_the_tier_is_a_pure_function_of_its_two_date_inputs(self):
        """Determinism is load-bearing: re-gating the same plan must always give
        the same verdict, so no wall clock may leak into this function."""
        import inspect

        from engine.marketing import sentinel

        # The docstring NAMES `datetime.now()` as the thing not to do, so scan
        # the code with the docstring removed — otherwise the warning trips the
        # guard the warning is about.
        src = inspect.getsource(sentinel.resolve_ramp_tier).replace(
            sentinel.resolve_ramp_tier.__doc__ or "", "")
        for banned in ("now(", "today(", "utcnow", "time.time"):
            assert banned not in src, (
                f"resolve_ramp_tier reads a wall clock ({banned}) — the tier "
                f"must come from (created, as_of) alone")
        first = sentinel.resolve_ramp_tier(
            _minus(5), _AS_OF, weeks_1_2_days=5, weeks_3_4_days=10)
        assert first == sentinel.resolve_ramp_tier(
            _minus(5), _AS_OF, weeks_1_2_days=5, weeks_3_4_days=10)


# ─────────────────────────────────────────────────────────────────────────────
# 2. graduate_after_days clamps to the CONFIGURED boundary, not the constant
# ─────────────────────────────────────────────────────────────────────────────

class TestGraduationClamp:

    def test_twenty_one_is_no_longer_clamped_up_to_twenty_eight(self):
        """THE defect: the clamp floor was the hardcoded 28, so the shipped
        `graduate_after_days: 21` would have been read as 28."""
        from engine.marketing.sentinel import effective_graduate_after_days
        assert effective_graduate_after_days(
            SHIPPED_GRADUATE_AFTER_DAYS,
            weeks_3_4_days=SHIPPED_WEEKS_3_4_DAYS) == SHIPPED_GRADUATE_AFTER_DAYS

    def test_it_still_clamps_to_the_configured_boundary(self):
        """The knob stays honest at every value: below the tier-2 boundary it is
        inert (the two age branches fire first), so it is raised to the boundary
        rather than silently reinterpreted."""
        from engine.marketing.sentinel import effective_graduate_after_days
        assert effective_graduate_after_days(3, weeks_3_4_days=10) == 10
        assert effective_graduate_after_days(0, weeks_3_4_days=10) == 10

    def test_the_legacy_clamp_is_unchanged_with_no_boundary_argument(self):
        from engine.marketing.sentinel import effective_graduate_after_days
        assert effective_graduate_after_days(20) == LEGACY_WEEKS_3_4_DAYS
        assert effective_graduate_after_days(56) == 56

    def test_a_twenty_one_day_account_graduates_on_the_fast_schedule(self):
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg_with(_tier_row(weeks_1_2_days=5, weeks_3_4_days=10,
                                  graduate_after_days=21),
                        created=_minus(21))
        report = resolve_ramp(cfg, _AS_OF, announce=False)
        assert report["graduate_after_days"] == 21, (
            "the clamp raised a configured 21 — the fast schedule is inert")
        assert report["accounts"]["newdesk"]["tier"] == "graduated"

    def test_the_resolved_schedule_is_reported(self):
        """A clamped or fallen-back config must stay VISIBLE rather than being
        silently reinterpreted — same contract graduate_after_days already had."""
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg_with(_tier_row(weeks_1_2_days=5, weeks_3_4_days=10),
                        created=_minus(1))
        report = resolve_ramp(cfg, _AS_OF, announce=False)
        assert report["weeks_1_2_days"] == 5
        assert report["weeks_3_4_days"] == 10

    def test_the_gate_report_carries_the_resolved_schedule(self):
        from engine.marketing.sentinel import gate_plan
        cfg = _cfg_with(_tier_row(weeks_1_2_days=5, weeks_3_4_days=10),
                        created=_minus(6))
        plan = {"as_of": _AS_OF, "accounts": [
            {"account_id": "newdesk", "items": [
                {"id": "i1", "type": "note", "slot": "D1-a",
                 "headline": "A note", "body": "Nothing to see."},
            ]},
        ]}
        _annotated, report = gate_plan(plan, cfg, receipts_age_days=1,
                                       graded_window=[])
        ramp = report["checks"]["ramp"]
        assert ramp["weeks_1_2_days"] == 5
        assert ramp["weeks_3_4_days"] == 10
        assert ramp["graduate_after_days"] == 21


# ─────────────────────────────────────────────────────────────────────────────
# 3. An incoherent pair reverts to the defaults AND annotates at line start
# ─────────────────────────────────────────────────────────────────────────────

class TestIncoherentBoundaries:

    @pytest.mark.parametrize("w12,w34", [
        (10, 5),      # inverted
        (10, 10),     # equal — deletes weeks_3_4 entirely
        (0, 10),      # zero-length first tier
        (-3, 10),     # negative
        (5, 0),
    ])
    def test_an_incoherent_pair_reverts_BOTH_to_the_defaults(self, w12, w34):
        """Half-applying a typo would hand a brand-new account a tier it has not
        earned, so both values revert together."""
        from engine.marketing.sentinel import resolve_ramp_boundaries
        assert resolve_ramp_boundaries(
            {"weeks_1_2_days": w12, "weeks_3_4_days": w34},
            announce=False) == (LEGACY_WEEKS_1_2_DAYS, LEGACY_WEEKS_3_4_DAYS)

    def test_the_incoherent_pair_annotates_at_line_start(self, capsys):
        """A bare line-start ``print`` is LOAD-BEARING: every builder here logs
        with a prefixing format, so ``log.warning("::warning …")`` emits
        ``WARNING ::warning …`` and GitHub silently drops it."""
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg_with(_tier_row(weeks_1_2_days=30, weeks_3_4_days=10),
                        created=_minus(6))
        resolve_ramp(cfg, _AS_OF)
        out = capsys.readouterr().out
        hits = [ln for ln in out.splitlines()
                if "sentinel-ramp-boundaries-incoherent" in ln]
        assert hits, f"no boundary annotation in {out!r}"
        assert hits[0].startswith("::"), (
            f"annotation is not at line start — GitHub drops it: {hits[0]!r}")
        assert len(hits) == 1, "the same config defect printed more than once"

    def test_the_incoherent_pair_resolves_tiers_on_the_default_ladder(self):
        """The consequence, not just the message: a 6-day-old desk under a broken
        pair is back on the 14-day first tier, NOT on the fast one."""
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg_with(_tier_row(weeks_1_2_days=30, weeks_3_4_days=10),
                        created=_minus(6))
        report = resolve_ramp(cfg, _AS_OF, announce=False)
        assert report["accounts"]["newdesk"]["tier"] == "weeks_1_2"
        assert report["weeks_1_2_days"] == LEGACY_WEEKS_1_2_DAYS
        assert report["weeks_3_4_days"] == LEGACY_WEEKS_3_4_DAYS

    def test_a_config_with_no_ramp_table_stays_silent(self, capsys):
        """Nothing is enforced, so nothing degraded — no warning."""
        from engine.marketing.sentinel import resolve_ramp
        cfg = _cfg_with({"weeks_1_2_days": 30, "weeks_3_4_days": 10},
                        created=_minus(6))
        resolve_ramp(cfg, _AS_OF)
        assert "sentinel-ramp-boundaries-incoherent" not in capsys.readouterr().out


# ─────────────────────────────────────────────────────────────────────────────
# 4. The SHIPPED config — the operator's actual complaint
# ─────────────────────────────────────────────────────────────────────────────

class TestTheShippedSchedule:

    def test_the_shipped_config_declares_the_fast_ladder(self, cfg):
        ramp = (cfg.get("sentinel") or {}).get("ramp") or {}
        assert ramp.get("weeks_1_2_days") == SHIPPED_WEEKS_1_2_DAYS
        assert ramp.get("weeks_3_4_days") == SHIPPED_WEEKS_3_4_DAYS
        assert ramp.get("graduate_after_days") == SHIPPED_GRADUATE_AFTER_DAYS

    def test_the_shipped_config_resolves_the_fast_ladder(self, cfg):
        """Read through the REAL resolver, so a code path that ignored the keys
        would be red here even with the config right."""
        from engine.marketing.sentinel import resolve_ramp
        report = resolve_ramp(cfg, _AS_OF, root=ROOT, announce=False)
        assert report["enforced"] is True
        assert report["weeks_1_2_days"] == SHIPPED_WEEKS_1_2_DAYS
        assert report["weeks_3_4_days"] == SHIPPED_WEEKS_3_4_DAYS
        assert report["graduate_after_days"] == SHIPPED_GRADUATE_AFTER_DAYS

    @pytest.mark.parametrize("age,tier", [
        (4, "weeks_1_2"),
        (5, "weeks_3_4"),        # was weeks_1_2 before the relaxation
        (10, "week_5_plus"),     # was weeks_1_2 before the relaxation
    ])
    def test_a_five_and_ten_day_old_desk_on_the_shipped_config(self, cfg, age, tier):
        """Every enabled desk, so this cannot pass by picking a lucky account."""
        from engine.marketing.accounts import effective_accounts
        from engine.marketing.sentinel import resolve_ramp

        desks = [a for a in effective_accounts(cfg, ROOT) if a.get("enabled")]
        assert desks, "no enabled desks — this test would assert nothing"
        for acct in desks:
            created = date.fromisoformat(str(acct["created"])[:10])
            as_of = (created + timedelta(days=age)).isoformat()
            row = resolve_ramp(cfg, as_of, root=ROOT,
                               announce=False)["accounts"][str(acct["id"])]
            assert row["age_days"] == age
            assert row["tier"] == tier, (
                f"{acct['id']} at {age} days resolved {row['tier']}, expected {tier}")

    def test_the_relaxation_only_ever_widens_a_desk(self, cfg):
        """Direction check across the whole first month: no age may resolve to a
        SMALLER daily cap than it did on the 14/28/56 schedule. A ramp
        'relaxation' that tightened some age band would be a volume regression
        hiding inside a volume fix."""
        import copy

        from engine.marketing.accounts import effective_accounts
        from engine.marketing.sentinel import resolve_ramp

        legacy = copy.deepcopy(cfg)
        legacy_ramp = legacy["sentinel"]["ramp"]
        legacy_ramp.pop("weeks_1_2_days", None)
        legacy_ramp.pop("weeks_3_4_days", None)
        legacy_ramp["graduate_after_days"] = 56
        legacy_ramp["weeks_1_2"]["max_posts_per_account_per_day"] = 10
        legacy_ramp["weeks_3_4"]["max_posts_per_account_per_day"] = 14

        desks = [a for a in effective_accounts(cfg, ROOT) if a.get("enabled")]
        for acct in desks:
            created = date.fromisoformat(str(acct["created"])[:10])
            for age in range(0, 31):
                as_of = (created + timedelta(days=age)).isoformat()
                now_cap = resolve_ramp(cfg, as_of, root=ROOT, announce=False)[
                    "accounts"][str(acct["id"])]["caps"][
                    "max_posts_per_account_per_day"]
                was_cap = resolve_ramp(legacy, as_of, root=ROOT, announce=False)[
                    "accounts"][str(acct["id"])]["caps"][
                    "max_posts_per_account_per_day"]
                if now_cap is None:            # unlimited bounds nothing
                    continue
                assert was_cap is not None and now_cap >= was_cap, (
                    f"{acct['id']} at {age} days: cap fell {was_cap} -> {now_cap}")

    def test_kelly_can_post_and_theme_list_is_never_banned_for_her(self, cfg):
        """The operator's complaint, stated as a property rather than a date.

        Kelly had never posted once, ever, because her only at-bat was a
        `theme_list` her account-age tier forbade. At NO age may her effective
        caps ban the format or hold her under the tier-1 volume.
        """
        from engine.marketing.sentinel import resolve_ramp

        raw = [a for a in ((cfg.get("desk_network") or {}).get("accounts") or [])
               if str(a.get("id")) == "kelly"]
        assert raw, "kelly is absent from desk_network — this test asserts nothing"
        created = date.fromisoformat(str(raw[0]["created"])[:10])

        for age in range(0, 31):
            as_of = (created + timedelta(days=age)).isoformat()
            caps = resolve_ramp(cfg, as_of, root=ROOT,
                                announce=False)["accounts"]["kelly"]["caps"]
            assert caps["theme_list_allowed"] is True, (
                f"kelly at {age} days is still banned from theme_list — the "
                f"format that cost her every post she ever had")
            cap = caps["max_posts_per_account_per_day"]
            assert cap is None or cap >= 14, (
                f"kelly at {age} days may post only {cap}/day")

    def test_kelly_is_on_the_second_tier_on_the_day_of_the_order(self, cfg):
        """Anchored to the operator's own date. She was `weeks_1_2` (10/day,
        theme_list banned); the relaxation puts her on `weeks_3_4`."""
        from engine.marketing.sentinel import resolve_ramp
        row = resolve_ramp(cfg, _AS_OF, root=ROOT,
                           announce=False)["accounts"]["kelly"]
        assert row["tier"] == "weeks_3_4"
        assert row["caps"]["max_posts_per_account_per_day"] == 18
        assert row["caps"]["theme_list_allowed"] is True

    def test_no_enabled_desk_is_banned_from_theme_list_today(self, cfg):
        """The whole point of the edit, network-wide, on the order's own date."""
        from engine.marketing.accounts import effective_accounts
        from engine.marketing.sentinel import resolve_ramp

        report = resolve_ramp(cfg, _AS_OF, root=ROOT, announce=False)
        desks = [a for a in effective_accounts(cfg, ROOT) if a.get("enabled")]
        assert desks, "no enabled desks — this test would assert nothing"
        banned = [str(a["id"]) for a in desks
                  if not report["accounts"][str(a["id"])]["caps"]["theme_list_allowed"]]
        assert not banned, f"desks still banned from theme_list: {banned}"

    def test_the_shipped_config_never_annotates_its_own_ramp(self, capsys):
        """A committed config that trips its own ::warning is a defect that would
        print on every nightly run."""
        from engine.marketing.sentinel import resolve_ramp
        cfg = yaml.safe_load(
            (ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
        resolve_ramp(cfg, _AS_OF, root=ROOT)
        out = capsys.readouterr().out
        assert "sentinel-ramp-boundaries-incoherent" not in out
        assert "sentinel-ramp-created-missing" not in out
        assert "sentinel-ramp-tier-value-unparseable" not in out

    def test_the_spacing_floor_did_not_move(self, cfg):
        """NOT part of the relaxation and deliberately so: min_minutes_between_posts
        is coupled to the 28-rung 30-minute Pacific ladder
        (outbox._LADDER_PT_TIMES / content_studio._LADDER_SLOTS), so changing it
        desyncs slot times from the clock table."""
        from engine.marketing import outbox as OB

        ramp = (cfg.get("sentinel") or {}).get("ramp") or {}
        tiers = {k: v for k, v in ramp.items()
                 if isinstance(v, dict) and k != "account_overrides"}
        assert tiers
        for name, row in tiers.items():
            assert int(row["min_minutes_between_posts"]) == int(OB._LADDER_STEP_MIN), (
                f"sentinel.ramp.{name}.min_minutes_between_posts drifted off the "
                f"ladder step")
