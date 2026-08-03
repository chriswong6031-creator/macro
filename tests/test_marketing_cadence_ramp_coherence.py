"""tests/test_marketing_cadence_ramp_coherence.py — the persona spec may never be
the throttle.

WHAT WENT WRONG. `engine/marketing/cadence_resolver.py` is the per-account law
(XG-W2) and `sentinel.ramp` is the per-account age ramp (D08). They are ANDed at
post time, so whichever is smaller is what a desk actually gets. Nobody kept them
in the same units. On 2026-07-28 the ramp said 10 posts/day for a new desk and 20
for the flagship, #3904 rebuilt the ladder (28 rungs at 30 min) around exactly
that, and every persona spec still carried the W1 declaration — 3-4 posts/day at
a 120-180 MINUTE spacing floor. The resolver was running in SHADOW, so the
mismatch cost nothing and showed up only as log lines:

    flagship  posts_per_day=4  daily_budget=4  posted_today=3  would_refuse: min_spacing
    sophia    posts_per_day=3  daily_budget=3  posted_today=2  would_refuse: min_spacing
    founder   posts_per_day=3  daily_budget=3  posted_today=3  would_refuse: daily_cap

Arming the resolver on those numbers would have dropped the network from 70
posts/day to 20 and made every cap #3904 raised dead config. This suite is the
standing guard so a future spec edit cannot silently re-introduce that throttle.

THE FOUR RELATIONS THIS SUITE PINS.

  1. VOLUME.  posts_per_day >= every ramp cap the desk will ever resolve to.
     Checked against the REAL resolve_ramp at the desk's own created date + 0 /
     14 / 28 / graduate_after_days, so tier merging and per-account overrides are
     exercised rather than re-implemented here. The ramp stays the governor: a
     week-1 desk is held at 10/day by its TIER, which is visible in the gate
     report, not by a hand-written number buried in a persona file.

  2. LADDER FIT.  min_spacing_min * posts_per_day must fit inside the ladder
     window (28 rungs, 4:00 AM-5:30 PM PT = 810 minutes). A floor larger than
     ladder_span / posts_per_day is self-contradictory: the desk is told to post
     n times inside a window that cannot hold n posts at that spacing. Also
     checked with jitter folded in, because the resolver's real requirement is
     `min_spacing_min + jitter`, not `min_spacing_min`.

  3. SWEEP QUANTISATION.  min_spacing_min + jitter_min <= one ladder rung minus
     publish.post_jitter_max_min. This is the relation that actually decides
     throughput and it is invisible from the config alone. The publisher sweeps
     every 30 minutes and books each post at `now + jitter` (up to
     post_jitter_max_min = 7), while the resolver measures elapsed time from that
     BOOKED stamp at the next sweep — so the gap it sees is 30 - 7 = 23 minutes
     at worst. A floor above 23 makes every post miss its next rung and wait two,
     halving the desk's day while every number in the config still reads fine.
     Measured: min_spacing_min 30 (which merely MATCHES the ramp's stated
     min_minutes_between_posts) yields ~15 posts/day against a 20/day tier.

  4. THE SESSION FENCE.  A `cadence.session` desk can be capped by its territory
     windows long before either volume number binds — the fence is ANDed too.
     Cici's original windows overlapped the publisher's own cron window for only
     3.5 hours, which held her to ~11 slots however high posts_per_day went. The
     fence must leave at least as many sweeps as the desk's widest ramp cap.

Plus the operator's standing target (2026-07-28: >= 10 posts/day per account, 20
for the flagship) asserted against the ramp itself, and a tripwire pinning the
ladder/cron constants the arithmetic above is derived from — so a future ladder
or cron change turns this suite RED instead of quietly making it vacuous.

CONVENTIONS. Reads the committed config only; no wall clock, no I/O outside the
repo, no network. Import closure is stdlib + pyyaml so it runs in full in the
marketing-engine lane.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

#: Operator standing target, 2026-07-28: at least 10 posts/day per account, 20
#: for the flagship. #3904 rebuilt the ladder and the ramp caps around exactly
#: these numbers.
OPERATOR_MIN_POSTS_PER_DAY = 10
OPERATOR_FLAGSHIP_POSTS_PER_DAY = 20

_PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "marketing-publish.yml"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def enabled_desks(cfg) -> list[dict]:
    """Every desk that is live right now — desk_network intent AND the operator
    override file, read through the same helper the publisher uses."""
    from engine.marketing.accounts import effective_accounts

    desks = [a for a in effective_accounts(cfg, ROOT) if a.get("enabled")]
    # Vacuous-green guard: an empty list would pass every assertion below.
    assert desks, "no enabled desks resolved — this suite would be asserting nothing"
    return desks


@pytest.fixture(scope="module")
def profiles(cfg) -> dict:
    from engine.marketing import cadence_resolver as CR
    from engine.marketing import personas as P

    return CR.load_profiles(specs=P.load_all(ROOT))


def _ladder_constants():
    """The shipped ladder geometry, read from the module that owns it."""
    from engine.marketing import outbox as OB

    step = int(OB._LADDER_STEP_MIN)
    slots = int(OB._LADDER_N_SLOTS)
    return step, slots, step * (slots - 1)          # step, rungs, span in minutes


def _reachable_caps(cfg, acct: dict) -> dict[str, "int | None"]:
    """``{tier: max_posts_per_account_per_day}`` for every tier this desk ages into.

    Resolved through the REAL sentinel.resolve_ramp at the desk's own created date
    plus each tier boundary, so tier merging, junk-value handling and
    ``account_overrides`` all run exactly as they do in the publisher. ``None`` is
    the ramp's "unlimited" and imposes no bound.
    """
    from engine.marketing.sentinel import resolve_ramp, resolve_ramp_boundaries

    created = date.fromisoformat(str(acct["created"])[:10])
    ramp_cfg = ((cfg.get("sentinel") or {}).get("ramp") or {})
    grad = int(ramp_cfg.get("graduate_after_days", 56))
    # OFFSETS DERIVE FROM THE CONFIGURED BOUNDARIES, never the old literals
    # (2026-08-03). They were hardcoded (0, 14, 28, grad) against the 14/28
    # schedule. The fast ramp moved the tiers to 5/10, at which those offsets
    # land on weeks_1_2 / week_5_plus / graduated / graduated — `weeks_3_4`
    # stopped being sampled at all and this suite went quietly green over a tier
    # it no longer covered. A coherence guard that skips a tier is not a guard.
    _w12, _w34 = resolve_ramp_boundaries(ramp_cfg, announce=False)
    out: dict[str, int | None] = {}
    for offset in (0, _w12, _w34, grad):
        ramp = resolve_ramp(cfg, (created + timedelta(days=offset)).isoformat(),
                            root=ROOT, announce=False)
        entry = ramp["accounts"][str(acct["id"])]
        out[entry["tier"]] = entry["caps"]["max_posts_per_account_per_day"]
    return out


def _bounded_max_cap(caps: dict[str, "int | None"]) -> int:
    """The widest REAL cap in a reachable-cap map (unlimited tiers bound nothing)."""
    real = [c for c in caps.values() if c is not None]
    return max(real) if real else 0


def _cron_field(field: str) -> list[int]:
    """Expand one crontab field (``0,30`` / ``0,1,11-23``) to sorted ints."""
    out: set[int] = set()
    for part in field.split(","):
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
            out.update(range(lo, hi + 1))
        else:
            out.add(int(part))
    return sorted(out)


def _publish_cron() -> str:
    """The publisher's schedule line, read from the workflow that owns it."""
    text = _PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    crons = re.findall(r'^\s*-\s*cron:\s*"([^"]+)"', text, flags=re.MULTILINE)
    assert len(crons) == 1, f"expected exactly one publish cron, got {crons!r}"
    return crons[0]


def _sweep_times_utc() -> list[tuple[int, int]]:
    """``[(hour, minute), ...]`` UTC for one day of publisher sweeps."""
    minute_f, hour_f = _publish_cron().split()[:2]
    return [(h, m) for h in _cron_field(hour_f) for m in _cron_field(minute_f)]


def _in_session_sweeps_per_local_day(profile) -> int:
    """How many publisher sweeps land inside ``profile``'s session on one LOCAL day.

    A session desk's local day straddles the UTC day (Cici's Hong Kong evening
    leg starts before the UTC date rolls), so the sweeps are expanded across three
    UTC days and grouped by LOCAL date; the middle local day is the only one the
    expansion fully covers.
    """
    from engine.marketing.cadence_resolver import _local, in_session

    anchor = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    target = _local(anchor, profile.tz).date()
    count = 0
    for day_offset in (-1, 0, 1):
        day = anchor.date() + timedelta(days=day_offset)
        for hour, minute in _sweep_times_utc():
            when = datetime(day.year, day.month, day.day, hour, minute,
                            tzinfo=timezone.utc)
            if _local(when, profile.tz).date() != target:
                continue
            if in_session(profile, when):
                count += 1
    return count


# ─────────────────────────────────────────────────────────────────────────────
# 0. The constants the arithmetic below is derived from
# ─────────────────────────────────────────────────────────────────────────────

def test_the_ladder_and_cron_constants_this_suite_assumes_are_the_shipped_ones():
    """Tripwire. Every relation below is derived from the ladder geometry and the
    publisher's sweep grid. If either moves and this suite keeps its old numbers,
    it would still pass while guarding a cadence that no longer exists — the exact
    way the persona specs themselves went stale. Change these deliberately."""
    step, slots, span = _ladder_constants()
    assert (step, slots, span) == (30, 28, 810), (
        "the ladder moved (30-min step, 28 rungs, 4:00 AM-5:30 PM PT = 810 min). "
        "Re-derive the spacing relations in this suite before re-pinning it."
    )
    assert _publish_cron() == "0,30 0,1,11-23 * * *", (
        "the publisher's sweep grid moved — the sweep-quantisation relation and "
        "the session-fence count are both computed from it"
    )
    # 30 sweeps per UTC day, which is what has to hold a 20-post desk day.
    assert len(_sweep_times_utc()) == 30


def test_every_ramp_tier_paces_to_the_ladder_step(cfg):
    """The ramp's own spacing knob and the ladder step are the same number by
    construction (#3904 tightened the ladder to 30 min *because* the ramp says
    30). A tier row that drifts off it means the ladder can no longer deliver
    that tier's volume."""
    step, _slots, _span = _ladder_constants()
    ramp = (cfg.get("sentinel") or {}).get("ramp") or {}
    tiers = {k: v for k, v in ramp.items() if isinstance(v, dict) and k != "account_overrides"}
    assert tiers, "sentinel.ramp has no tier rows — the ramp would be a no-op"
    for name, row in tiers.items():
        if "min_minutes_between_posts" in row:
            assert int(row["min_minutes_between_posts"]) == step, (
                f"sentinel.ramp.{name}.min_minutes_between_posts is "
                f"{row['min_minutes_between_posts']}, ladder step is {step}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Volume — the spec must clear every tier the desk will reach
# ─────────────────────────────────────────────────────────────────────────────

def test_every_enabled_desk_has_a_cadence_profile(cfg, enabled_desks, profiles):
    """An enabled desk with no usable cadence block makes the resolver ABSTAIN for
    it — which is safe, but means none of the relations below are enforced for
    that desk. Enabled and specced must move together."""
    missing = [a["id"] for a in enabled_desks if a["id"] not in profiles]
    assert not missing, f"enabled desks with no cadence profile: {missing}"


def test_every_enabled_desk_declares_a_created_date(cfg, enabled_desks):
    """resolve_ramp fails CLOSED to weeks_1_2 without one, so a missing date reads
    as a permanently cold desk and the reachable-cap map below would be wrong."""
    missing = [a["id"] for a in enabled_desks if not a.get("created")]
    assert not missing, f"enabled desks with no created date: {missing}"


def test_spec_posts_per_day_clears_every_ramp_tier_the_desk_will_reach(
        cfg, enabled_desks, profiles):
    """THE regression this suite exists for. posts_per_day below a tier cap means
    the SPEC is the throttle, silently, for as long as nobody reads the shadow
    log."""
    failures = []
    for acct in enabled_desks:
        acct_id = str(acct["id"])
        prof = profiles[acct_id]
        if prof.posts_per_day < 0:
            continue                                  # negative = unlimited
        for tier, cap in _reachable_caps(cfg, acct).items():
            if cap is None:
                continue                              # unlimited tier bounds nothing
            if prof.posts_per_day < cap:
                failures.append(
                    f"{acct_id}: spec posts_per_day={prof.posts_per_day} < "
                    f"{tier} ramp cap {cap} — the spec would throttle the tier"
                )
    assert not failures, "\n".join(failures)


def test_the_ramp_still_delivers_the_operator_standing_target(cfg, enabled_desks):
    """The other direction: the ramp is the governor, so IT has to carry the
    operator's 2026-07-28 target (>= 10/day per account, 20 for the flagship). A
    ramp edit that drops below it is as much a volume regression as a spec one."""
    for acct in enabled_desks:
        acct_id = str(acct["id"])
        caps = _reachable_caps(cfg, acct)
        widest = _bounded_max_cap(caps)
        unlimited = any(c is None for c in caps.values())
        want = (OPERATOR_FLAGSHIP_POSTS_PER_DAY if acct_id == "flagship"
                else OPERATOR_MIN_POSTS_PER_DAY)
        assert unlimited or widest >= want, (
            f"{acct_id}: widest reachable ramp cap {widest} < operator target {want}"
        )
    flagship = next((a for a in enabled_desks if str(a["id"]) == "flagship"), None)
    if flagship is not None:
        # The flagship's account_override is meant to apply at EVERY age, so it is
        # not enough for it to reach 20 eventually.
        for tier, cap in _reachable_caps(cfg, flagship).items():
            assert cap is None or cap >= OPERATOR_FLAGSHIP_POSTS_PER_DAY, (
                f"flagship {tier} cap {cap} < {OPERATOR_FLAGSHIP_POSTS_PER_DAY}; the "
                f"account_overrides entry is supposed to hold at every tier"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 2 + 3. Spacing — the ladder window, and the sweep the resolver actually sees
# ─────────────────────────────────────────────────────────────────────────────

def test_spacing_times_volume_fits_inside_the_ladder_window(enabled_desks, profiles):
    """min_spacing_min larger than ladder_span / posts_per_day is self-contradictory:
    the spec asks for n posts in a window that cannot hold n posts at that floor."""
    _step, _slots, span = _ladder_constants()
    failures = []
    for acct in enabled_desks:
        acct_id = str(acct["id"])
        prof = profiles[acct_id]
        if prof.posts_per_day < 0:
            continue
        need = prof.min_spacing_min * prof.posts_per_day
        if need > span:
            failures.append(
                f"{acct_id}: min_spacing_min {prof.min_spacing_min} x posts_per_day "
                f"{prof.posts_per_day} = {need} min > the {span}-min ladder window"
            )
        # The resolver's real requirement is min_spacing_min + jitter (jitter is
        # ADDED to the floor, never subtracted), so the same relation has to hold
        # at the top of the jitter range.
        need_j = (prof.min_spacing_min + prof.jitter_min) * prof.posts_per_day
        if need_j > span:
            failures.append(
                f"{acct_id}: (min_spacing_min {prof.min_spacing_min} + jitter_min "
                f"{prof.jitter_min}) x posts_per_day {prof.posts_per_day} = {need_j} "
                f"min > the {span}-min ladder window"
            )
    assert not failures, "\n".join(failures)


def test_the_spacing_floor_fits_inside_one_sweep_minus_the_send_jitter(
        cfg, enabled_desks, profiles):
    """The relation that decides real throughput, and the one no config value
    shows you.

    The publisher sweeps every ladder step, books each post at ``now + jitter``
    (publish.post_jitter_max_min), and the resolver measures elapsed time from that
    BOOKED stamp — so at the next sweep the gap it sees is ``step - send_jitter``
    at worst. A floor above that refuses the next rung and the desk waits two,
    running at half cadence with every number in the config still looking right.
    Measured on the shipped grid: a 30-minute floor (which merely MATCHES the
    ramp's stated min_minutes_between_posts) delivers ~15 posts/day against a
    20/day tier.
    """
    step, _slots, _span = _ladder_constants()
    send_jitter = int((cfg.get("publish") or {}).get("post_jitter_max_min", 0))
    budget = step - send_jitter
    failures = []
    for acct in enabled_desks:
        acct_id = str(acct["id"])
        prof = profiles[acct_id]
        worst = prof.min_spacing_min + prof.jitter_min
        if worst > budget:
            failures.append(
                f"{acct_id}: min_spacing_min {prof.min_spacing_min} + jitter_min "
                f"{prof.jitter_min} = {worst} min > {budget} min "
                f"(ladder step {step} - send jitter {send_jitter}); every post "
                f"would miss its next rung"
            )
    assert not failures, "\n".join(failures)


def test_the_global_floor_never_outranks_a_per_account_floor(cfg, enabled_desks, profiles):
    """#3924 removed the 10-minute GLOBAL floor because it throttled seven desks as
    if they were one; the per-account floor is its correct replacement. If the
    global floor were ever raised back above a desk's own floor, the network would
    be back to pacing as a single account and the spec would stop mattering."""
    global_floor = int((cfg.get("publish") or {}).get("min_minutes_between_any_posts", 0))
    for acct in enabled_desks:
        acct_id = str(acct["id"])
        prof = profiles[acct_id]
        assert global_floor <= prof.min_spacing_min, (
            f"publish.min_minutes_between_any_posts={global_floor} >= {acct_id}'s own "
            f"min_spacing_min={prof.min_spacing_min}: the global floor is pacing the "
            f"desk again (#3924)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. The session fence is ANDed too
# ─────────────────────────────────────────────────────────────────────────────

def test_a_session_fence_is_never_the_binding_cap(cfg, enabled_desks, profiles):
    """A territory clock weights a desk's day; it must not CAP it below the ramp.

    Cici's windows overlapped the publisher's cron window for 3.5 hours, which
    held her to ~11 slots no matter how high posts_per_day went — the fence, not
    the ramp, was her real ceiling, and nothing in either config said so.
    """
    for acct in enabled_desks:
        acct_id = str(acct["id"])
        prof = profiles[acct_id]
        if not prof.has_session:
            continue
        reachable = _bounded_max_cap(_reachable_caps(cfg, acct))
        available = (_in_session_sweeps_per_local_day(prof)
                     + prof.outside_window_posts_per_day)
        assert available >= reachable, (
            f"{acct_id}: {available} publisher sweeps per local day are reachable "
            f"({_in_session_sweeps_per_local_day(prof)} inside the session windows + "
            f"{prof.outside_window_posts_per_day} outside-window allowance), but its "
            f"widest ramp cap is {reachable} — the session fence is the real cap"
        )


def test_a_session_fence_is_still_a_fence(enabled_desks, profiles):
    """The other half. Widening a window until it swallows the whole publishing
    day makes the territory clock decorative, which is precisely the failure
    `cadence.session` was added to end."""
    for acct in enabled_desks:
        acct_id = str(acct["id"])
        prof = profiles[acct_id]
        if not prof.has_session:
            continue
        total = len(_sweep_times_utc())
        inside = _in_session_sweeps_per_local_day(prof)
        assert inside < total, (
            f"{acct_id}: every one of the {total} daily sweeps is in-session — the "
            f"windows fence nothing"
        )
        assert prof.outside_window_posts_per_day < prof.posts_per_day, (
            f"{acct_id}: outside_window_posts_per_day="
            f"{prof.outside_window_posts_per_day} vs posts_per_day="
            f"{prof.posts_per_day} — the allowance makes the windows decorative"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Weekend shaping must not fall under the operator's floor
# ─────────────────────────────────────────────────────────────────────────────

def test_weekend_shaping_still_clears_the_operator_daily_floor(cfg, enabled_desks, profiles):
    """weekend_shape multiplies posts_per_day, so it is a volume number too — and
    the one that is easiest to leave behind, because it reads as a realism knob.
    At 20 posts/day `light` (0.34) resolves to 7, under the operator's floor of 10;
    `medium` (0.67) resolves to 13."""
    from engine.marketing.cadence_resolver import daily_budget, resolver_config

    factors = resolver_config(cfg)["weekend_factors"]
    saturday = datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc)
    sunday = datetime(2026, 8, 2, 18, 0, tzinfo=timezone.utc)
    for acct in enabled_desks:
        acct_id = str(acct["id"])
        prof = profiles[acct_id]
        if prof.posts_per_day < 0:
            continue
        for when, label in ((saturday, "Saturday"), (sunday, "Sunday")):
            budget = daily_budget(prof, when, weekend_factors=factors)
            assert budget >= OPERATOR_MIN_POSTS_PER_DAY, (
                f"{acct_id}: weekend_shape={prof.weekend_shape} resolves to {budget} "
                f"posts on a {label}, under the operator floor of "
                f"{OPERATOR_MIN_POSTS_PER_DAY}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 6. The arming decision, recorded
# ─────────────────────────────────────────────────────────────────────────────

def test_the_shipped_config_arms_the_resolver(cfg):
    """ARMED 2026-07-28, after the specs above were reconciled with the ramp.

    It landed dark on purpose (XG-W2) because arming it against the W1
    declarations would have cut the network from 70 posts/day to 20. With the
    specs corrected the resolver no longer binds before the ramp on a weekday, and
    what it adds is the thing #3924 showed was missing: a PER-ACCOUNT spacing
    floor. Removing the 10-minute global floor left only a 4-minute network floor,
    so nothing bounded one desk's burstiness — and per-account burstiness is what
    an automation heuristic reads. Disarming is a one-key change; do it knowing
    that it removes the only per-account spacing bound the stack has.
    """
    from engine.marketing import cadence_resolver as CR

    assert CR.resolver_config(cfg)["enabled"] is True, (
        "the cadence resolver is the per-account bound the 10-min global floor was "
        "wrongly standing in for (#3924); disarming leaves none"
    )
    # The machinery around it is unchanged.
    assert cfg["cadence_resolver"]["exempt_immediate"] is True
    assert set(cfg["cadence_resolver"]["weekend_factors"]) == {"light", "medium", "full"}


def test_arming_does_not_bind_before_the_ramp_on_a_weekday(cfg, enabled_desks, profiles):
    """End-to-end statement of the whole suite: for every enabled desk, on a
    weekday, the resolver's own daily budget is at or above the ramp cap that
    governs it — so the ARMED resolver changes the network's volume by nothing and
    only adds pacing."""
    from engine.marketing.cadence_resolver import daily_budget, resolver_config
    from engine.marketing.outbox import effective_cap_for

    factors = resolver_config(cfg)["weekend_factors"]
    wednesday = datetime(2026, 7, 29, 18, 0, tzinfo=timezone.utc)
    as_of = "2026-07-29"
    for acct in enabled_desks:
        acct_id = str(acct["id"])
        prof = profiles[acct_id]
        cap = effective_cap_for(cfg, acct_id, as_of, root=ROOT)
        if cap < 0:
            continue                                   # unlimited ramp side
        budget = daily_budget(prof, wednesday, weekend_factors=factors)
        assert budget < 0 or budget >= cap, (
            f"{acct_id}: resolver weekday budget {budget} < ramp cap {cap} — arming "
            f"the resolver would throttle this desk below its tier"
        )
