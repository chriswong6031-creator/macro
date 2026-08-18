"""Pins the nightly-liveness dead-man switch against the 2026-08-11/12 outage.

Every fixture below is a shape this repository actually produced during the two
sessions the US nightly went dark. The point of the suite is that each check fails
for its OWN reason: if you delete check A, `test_strand_is_invisible_to_data_checks`
is the one that reds, and it reds specifically because the data budgets are still
satisfied at that moment. That is the defect the guard exists for.

Fixture dates are CONSTANTS with no relation to the wall clock. A guard whose
fixtures age is a scheduled red.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_nightly_liveness import (  # noqa: E402
    DEFAULT_REPO,
    FIRE_BOUNDARY_UTC,
    MARKET_BOARDS,
    MAX_SESSIONS_BEHIND,
    WORKFLOW_FILE,
    evaluate,
    expected_fire_after,
    main,
)

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "nightly-liveness.yml"

# 08:00Z on 2026-08-12 — the first liveness slot after the 2026-08-11 bake was owed.
NOW = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)
# The store as it actually stood: frozen at the 2026-08-10 bake.
FROZEN = {"source_asof": "2026-08-10"}
ADVANCED = {"source_asof": "2026-08-11"}

# The last run that ever landed before the strand (real: 31444510694).
LAST_GOOD_RUN = {"created_at": "2026-08-11T00:00:55Z",
                 "status": "completed", "conclusion": "success"}


def _run(**kw):
    base = {"created_at": "2026-08-11T22:30:00Z", "status": "completed",
            "conclusion": "success"}
    base.update(kw)
    return base


# ── check A: the schedule stopped producing runs ────────────────────────────
def test_strand_is_invisible_to_data_checks():
    """The load-bearing test. One night into the strand the store is only ONE
    session behind — inside the freshness_sentinel budget AND nowhere near
    healthcheck's 96h. Check A was the only instrument that could see it when
    this guard was written; since 2026-08-17 the grace-expired path of check C
    ALSO sees it at this instant (08:00Z = boundary + STALE_GRACE exactly), and
    that overlap is deliberate defense in depth — A still fires first on earlier
    looks, names the strand mechanism, and works when the index is unreadable.
    The flat-budget path must still be quiet here (behind == 1, not > 1)."""
    report = evaluate([LAST_GOOD_RUN], FROZEN, NOW)
    assert report["ok"] is False
    assert any("NO RUN" in f for f in report["fail_reasons"])
    # If this ever reads > 1, the fixture has drifted and the test no longer pins
    # the "flat data budget is satisfied here" property that makes check A (and
    # the grace path) necessary.
    assert report["facts"]["sessions_behind"] == MAX_SESSIONS_BEHIND
    assert not any(f.startswith("STALE DATA:") for f in report["fail_reasons"])
    assert any("grace expired" in f for f in report["fail_reasons"])


def test_run_created_before_the_boundary_does_not_count():
    """A run for the PREVIOUS session must not satisfy this session's bake."""
    session, boundary = expected_fire_after(NOW)
    assert session.isoformat() == "2026-08-11"
    assert boundary.time() == FIRE_BOUNDARY_UTC
    just_before = evaluate(
        [_run(created_at="2026-08-11T21:59:59Z")], ADVANCED, NOW)
    just_after = evaluate(
        [_run(created_at="2026-08-11T22:00:01Z")], ADVANCED, NOW)
    assert just_before["ok"] is False
    assert just_after["ok"] is True


def test_est_regime_fire_after_utc_midnight_still_counts():
    """During EST the pair fires 23:30Z, and dispatch lag pushes real starts past
    00:00Z the next day (31444510694 was created 00:00:55Z). Those belong to the
    prior session's bake and must satisfy it."""
    report = evaluate([_run(created_at="2026-08-12T00:30:00Z")], ADVANCED, NOW)
    assert report["ok"] is True


# ── check B: runs created, none survived ────────────────────────────────────
def test_all_runs_cancelled_fails():
    """2026-08-12: six dispatches force-cancelled by a live fleet session."""
    report = evaluate(
        [_run(conclusion="cancelled"), _run(conclusion="cancelled")], FROZEN, NOW)
    assert report["ok"] is False
    assert any("NO SUCCESS" in f for f in report["fail_reasons"])


def test_queued_forever_is_indeterminate_not_a_breach():
    """A stranded run sits queued with zero jobs for hours. That is not yet proof
    of absence — check C is the backstop once the store falls far enough behind.
    (9.5h old at the 08:00Z look — under IN_FLIGHT_MAX_AGE by design.)"""
    report = evaluate([_run(status="queued", conclusion=None)], FROZEN, NOW)
    assert report["ok"] is True
    assert report["warnings"]


def test_in_flight_past_the_age_cap_is_a_wedge_breach():
    """2026-08-16/17: collect_tail queued on a runner label with no live runner
    held run 31977372592 open 24h+, pended the next night's cron slot behind its
    concurrency group, and froze every Prophet board — while the unconditional
    in-flight INDETERMINATE kept this guard quiet for two days. At the 14:00Z
    look the 22:30Z run is 15.5h old: past IN_FLIGHT_MAX_AGE, a positive
    observation of a wedge."""
    fourteen = datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc)
    report = evaluate([_run(status="queued", conclusion=None)], FROZEN, fourteen)
    assert report["ok"] is False
    assert any("WEDGED IN FLIGHT" in f for f in report["fail_reasons"])


def test_a_pre_boundary_hostage_run_is_still_seen():
    """A Thursday run still alive on Saturday has fallen out of `recent` — the
    age triage must scan the full fetched window, or the oldest (worst) hostages
    are exactly the ones that vanish from the verdict."""
    sat = datetime(2026, 8, 15, 8, 30, tzinfo=timezone.utc)  # expected: 08-14
    hostage = _run(created_at="2026-08-13T22:52:00Z", status="queued",
                   conclusion=None)
    report = evaluate([hostage], {"source_asof": "2026-08-13"}, sat)
    assert report["ok"] is False
    assert any("WEDGED IN FLIGHT" in f for f in report["fail_reasons"])


def test_weekend_missed_friday_pages_after_grace():
    """THE CANADA HOLE. A missed Friday bake reads '1 behind' all weekend under
    the flat budget, so it could not alarm before Tuesday — Canada served 08-11
    picks from 08-11 to 08-17 with zero noise. Saturday morning past the grace,
    with a READ run list and nothing alive, 1-behind is a breach."""
    sat = datetime(2026, 8, 15, 8, 30, tzinfo=timezone.utc)
    report = evaluate([], {"source_asof": "2026-08-13"}, sat)
    assert report["ok"] is False
    assert any("grace expired" in f for f in report["fail_reasons"])


def test_weekend_fresh_run_excuses_the_grace_path():
    """A slow-but-alive bake at the Saturday 08:30Z look is WAIT, not a page —
    the grace breach requires positive evidence that nothing is baking."""
    sat = datetime(2026, 8, 15, 8, 30, tzinfo=timezone.utc)
    fresh = _run(created_at="2026-08-15T04:00:00Z", status="in_progress",
                 conclusion=None)
    report = evaluate([fresh], {"source_asof": "2026-08-13"}, sat)
    assert report["ok"] is True


def test_grace_never_breaches_on_a_blind_run_list():
    """Blindness discipline holds for the grace path too: an unreadable run list
    cannot prove nothing is baking, so 1-behind stays INDETERMINATE."""
    sat = datetime(2026, 8, 15, 8, 30, tzinfo=timezone.utc)
    report = evaluate(None, {"source_asof": "2026-08-13"}, sat)
    assert report["ok"] is True


def test_one_success_among_failures_is_healthy():
    """Reruns are normal; the night is fine if anything landed."""
    report = evaluate(
        [_run(conclusion="cancelled"), _run(conclusion="success")], ADVANCED, NOW)
    assert report["ok"] is True


def test_cancelled_real_plus_surviving_gate_skip_is_not_a_bake():
    """2026-08-14/15: EDT 31848262472 cancelled/superseded, EST-guard
    31851452961 concluded success in ~5s and skipped every real job.

    A gate-skip success must not set baked=True. That misread is
    ``RAN GREEN BUT DID NOT ADVANCE`` — i.e. "the nightly ran".
    """
    cancelled = _run(
        id=31848262472, created_at="2026-08-14T22:52:00Z",
        event="schedule", conclusion="cancelled",
        display_title="daily 30 22 * * *",
    )
    skip = _run(
        id=31851452961, created_at="2026-08-14T23:45:00Z",
        event="schedule", conclusion="success",
        display_title="daily 30 23 * * *",
        run_started_at="2026-08-15T02:16:00Z",
        updated_at="2026-08-15T02:16:05Z",
    )
    later = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
    frozen = {"source_asof": "2026-08-13"}
    report = evaluate([cancelled, skip], frozen, later)
    assert report["ok"] is False
    assert any("NO SUCCESS" in f for f in report["fail_reasons"])
    assert not any("DID NOT ADVANCE" in f for f in report["fail_reasons"]), (
        "a gate-skip success must not count as the nightly having run"
    )
    assert 31851452961 in (report["facts"].get("gate_skips") or [])

    # The live API shape: display_title was just "daily", run_started_at == created_at.
    unlabelled = evaluate([
        _run(id=31848262472, created_at="2026-08-14T22:52:07Z",
             event="schedule", conclusion="cancelled", display_title="daily"),
        _run(id=31851452961, created_at="2026-08-14T23:45:40Z",
             event="schedule", conclusion="success", display_title="daily",
             run_started_at="2026-08-14T23:45:40Z",
             updated_at="2026-08-15T02:16:21Z"),
    ], frozen, later)
    assert unlabelled["ok"] is False
    assert any("NO SUCCESS" in f for f in unlabelled["fail_reasons"])
    assert not any("DID NOT ADVANCE" in f for f in unlabelled["fail_reasons"])


# ── check C: green run, store stood still ───────────────────────────────────
def test_green_run_that_did_not_advance_the_store_fails():
    """#4779: an absence of red is not a pass. A success whose store did not move
    is the one failure A and B are both blind to."""
    report = evaluate([_run()], FROZEN, NOW)
    assert report["ok"] is False
    assert any("DID NOT ADVANCE" in f for f in report["fail_reasons"])


def test_second_night_out_trips_the_coarse_budget_too():
    later = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)
    report = evaluate([LAST_GOOD_RUN], FROZEN, later)
    assert report["ok"] is False
    assert any("NO RUN" in f for f in report["fail_reasons"])
    assert any("STALE DATA" in f for f in report["fail_reasons"])


# ── blindness discipline ────────────────────────────────────────────────────
@pytest.mark.parametrize("runs,index", [
    (None, None),
    (None, FROZEN),
    ([_run()], None),
    ([_run()], {"source_asof": None}),
    ([_run()], {"source_asof": "not-a-date"}),
])
def test_blindness_is_never_a_breach(runs, index):
    """An unreadable API, a missing artifact and an unparseable stamp all mean the
    guard cannot see — never that the pipeline is dead. A watchdog that cries wolf
    when blind gets muted, and then it is not a watchdog."""
    report = evaluate(runs, index, NOW)
    assert report["ok"] is True
    assert report["warnings"]


# ── calendar anchoring ──────────────────────────────────────────────────────
@pytest.mark.parametrize("now_iso,expected_session", [
    ("2026-08-15T08:00:00Z", "2026-08-14"),   # Saturday -> Friday
    ("2026-08-16T08:00:00Z", "2026-08-14"),   # Sunday   -> Friday
    ("2026-08-17T08:00:00Z", "2026-08-14"),   # Monday 08:00Z, Monday not closed yet
])
def test_weekend_cannot_manufacture_a_breach(now_iso, expected_session):
    now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    session, _ = expected_fire_after(now)
    assert session.isoformat() == expected_session
    friday_bake = _run(created_at="2026-08-14T22:30:00Z")
    report = evaluate([friday_bake], {"source_asof": "2026-08-14"}, now)
    assert report["ok"] is True


def test_july_4_holiday_cannot_manufacture_a_breach():
    """2026-07-03 is the observed Independence Day holiday; 07-02 is the last
    session. A bake owed for 07-02 satisfies the whole long weekend."""
    now = datetime(2026, 7, 5, 8, 0, tzinfo=timezone.utc)
    session, _ = expected_fire_after(now)
    assert session.isoformat() == "2026-07-02"
    report = evaluate([_run(created_at="2026-07-02T22:30:00Z")],
                      {"source_asof": "2026-07-02"}, now)
    assert report["ok"] is True


# ── wiring: the guard must actually be able to run ──────────────────────────
def test_default_repo_matches_the_git_remote():
    """A wrong slug 404s into INDETERMINATE — permanently blind, and silent about
    it. Pin the fallback to the real remote so a typo cannot ship."""
    url = subprocess.run(["git", "remote", "get-url", "origin"],
                         cwd=REPO_ROOT, capture_output=True, text=True,
                         check=True).stdout.strip()
    slug = url.removesuffix(".git").split("github.com", 1)[-1].lstrip(":/")
    assert DEFAULT_REPO == slug


def test_workflow_is_off_the_self_hosted_pool():
    """The whole point of a second watchdog: it must not share fate with the lane it
    watches. heartbeat.yml runs on macstudio — the same pool as daily.yml — so a pool
    outage silences the alarm and its subject together.

    Asserted against the PARSED runs-on, not the file text: the prose above the job
    discusses self-hosted runners at length, and a substring check over the raw
    source would pass or fail on the comments rather than on the wiring.
    """
    import yaml
    spec = yaml.safe_load(WORKFLOW.read_text())
    runners = [job.get("runs-on") for job in spec["jobs"].values()]
    assert runners, spec
    for runner in runners:
        labels = [runner] if isinstance(runner, str) else list(runner or [])
        assert labels == ["ubuntu-latest"], labels


def test_workflow_invokes_the_guard_and_passes_a_token():
    text = WORKFLOW.read_text()
    assert "scripts/check_nightly_liveness.py" in text
    assert "GITHUB_TOKEN" in text
    assert "actions: read" in text      # check A/B cannot list runs without it
    # The artifact check C reads must be in the sparse checkout.
    assert "site/prophet/index.json" in text


def test_workflow_watches_the_authoritative_build():
    """Build A (closing-bell) ran green through the whole outage while the board it
    re-rendered still read price_through=2026-08-10. Watching it would have proven
    nothing."""
    assert WORKFLOW_FILE == "daily.yml"


def test_selftest_passes():
    proc = subprocess.run(
        [sys.executable, "scripts/check_nightly_liveness.py", "--selftest"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout


def test_registered_in_the_house_law_registry():
    """An unregistered scripts/check_*.py is a HARD fail in check_house_law_registry."""
    import yaml
    registry = yaml.safe_load(
        (REPO_ROOT / "config" / "house_law_checks.yml").read_text())
    entry = next(
        (e for e in registry["checks"]
         if e.get("check_script") == "scripts/check_nightly_liveness.py"), None)
    assert entry is not None, "guard is not registered"
    wiring = entry.get("ci_wiring") or []
    assert any(w.get("workflow") == ".github/workflows/nightly-liveness.yml"
               for w in wiring), "scheduled lane not registered"
    assert any(w.get("lane") == "pr_ci" for w in wiring), "no PR-CI lane registered"


def test_annotations_start_the_line(capsys, tmp_path):
    """GitHub silently drops an annotation that does not START the line, and every
    builder here logs with a prefixing format, so `log.warning("::error ...")` ships
    a guard that reviews as an alarm and produces nothing. Pin the bare-print form.

    Both fixtures fail in a time-INDEPENDENT direction: an empty run list is always
    "NO RUN", and a 2026-08-10 stamp only gets staler. No scheduled red here.
    """
    from scripts.check_nightly_liveness import main
    idx = tmp_path / "index.json"
    idx.write_text(json.dumps(FROZEN))
    runs = tmp_path / "runs.json"
    runs.write_text(json.dumps([]))
    rc = main(["--index-json", str(idx), "--runs-json", str(runs)])
    out = capsys.readouterr().out
    annotations = [ln for ln in out.splitlines()
                   if "::error" in ln or "::warning" in ln]
    assert annotations, out
    for line in annotations:
        assert line.startswith("::"), line
    assert rc == 1


# ── the 2026-08-13 first-live-night lesson: run conclusion is a LANE LATCH ──
#
# The first night this guard was evaluated against reality, the recovery bake
# concluded `cancelled` — engine's final commit step lost a push race against a
# main moving ~1/min, and one offrender lane was cancelled — while 17/19 jobs
# were green and the picks LANDED (asof advanced, 25 fresh plans). The as-shipped
# check B would have paged at 08:00Z about a healthy night. The program memory
# already knew this shape ("run-level cancelled/failure conclusions are
# single-lane latches"); the guard now does too: the DUAL-READ leads, the
# conclusion is the footnote.

def test_cancelled_run_with_advanced_store_warns_but_does_not_page():
    """Tonight's exact shape must be a warning, never an alarm."""
    report = evaluate([_run(conclusion="cancelled")], ADVANCED, NOW)
    assert report["ok"] is True
    assert any("LANE LATCH" in w for w in report["warnings"])
    assert not report["fail_reasons"]


def test_cancelled_run_with_behind_store_still_pages():
    """The downgrade requires the store to EXCUSE the conclusion — a cancelled
    run whose store is stale is still the 2026-08-12 dispatch signature."""
    report = evaluate([_run(conclusion="cancelled")], FROZEN, NOW)
    assert report["ok"] is False
    assert any("NO SUCCESS" in f for f in report["fail_reasons"])


def test_cancelled_run_with_unreadable_store_still_pages():
    """Blindness never softens a POSITIVE observation of failure: the only
    evidence that could downgrade it is evidence we do not have."""
    report = evaluate([_run(conclusion="cancelled")], None, NOW)
    assert report["ok"] is False
    assert any("cannot be read to excuse" in f for f in report["fail_reasons"])


# ── check D: the 2026-08-14 Canada freeze — five boards, five calendars ─────
#
# The board that broke was not the one anyone graded. site/factordata/canada_standouts.json
# held ``as_of=2026-08-13`` from 2026-08-14 through at least 08-18 while daily.yml ran
# green, the render lane re-committed the file nightly (so its git mtime was always
# minutes old), and its US, HK and mainland siblings advanced to 08-14. Checks A-C were
# all satisfied: A and B watch the lane, C watches ONE artifact, and that artifact
# belongs to a different market.
#
# Fixture dates are CONSTANTS. 2026-08-18T08:00Z is the first liveness slot at which the
# real freeze is provably a freeze rather than a lag: 08-13 is two completed TSX sessions
# behind (08-14 and 08-17), one past the budget.

D_NOW = datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc)
D_RUNS = [_run(created_at="2026-08-17T22:30:00Z")]        # the lane is GREEN throughout
D_INDEX = {"source_asof": "2026-08-17"}                   # and so is check C
FRESH_BOARDS = {spec["market"]: {"as_of": "2026-08-17"} for spec in MARKET_BOARDS}


def _boards(**overrides):
    return {**FRESH_BOARDS, **overrides}


def test_all_five_boards_fresh_is_healthy():
    report = evaluate(D_RUNS, D_INDEX, D_NOW, boards=_boards())
    assert report["ok"] is True
    assert not report["fail_reasons"], report


def test_canada_freeze_pages_and_names_its_market():
    """The load-bearing test. Everything else about this night is green — the lane ran,
    the Prophet store advanced, four boards are current — and the only observable is the
    Canadian stamp. If check D is deleted, this is the test that reds."""
    report = evaluate(D_RUNS, D_INDEX, D_NOW, boards=_boards(ca={"as_of": "2026-08-13"}))
    assert report["ok"] is False
    stale = [f for f in report["fail_reasons"] if "STALE BOARD" in f]
    assert len(stale) == 1, report["fail_reasons"]
    assert "[Canada]" in stale[0]
    assert "canada_standouts.json" in stale[0]
    assert report["facts"]["boards"]["ca"]["behind"] == 2
    # A green lane and a green check C must not be able to excuse it.
    assert not any("NO RUN" in f or "STALE DATA" in f for f in report["fail_reasons"])


def test_a_stale_board_does_not_smear_onto_its_siblings():
    report = evaluate(D_RUNS, D_INDEX, D_NOW, boards=_boards(ca={"as_of": "2026-08-13"}))
    for market in ("us", "cn", "hk"):
        assert report["facts"]["boards"][market]["behind"] == 0, market


def test_every_breach_message_names_a_market():
    """Five boards bake in one lane; an unlabelled 'STALE BOARD' would send the operator
    to whichever market they happened to think of first."""
    labels = {spec["label"] for spec in MARKET_BOARDS}
    report = evaluate(D_RUNS, D_INDEX, D_NOW,
                      boards=_boards(ca={"as_of": "2026-08-01"},
                                     us={"as_of": "2026-08-01"}))
    stale = [f for f in report["fail_reasons"] if "STALE BOARD" in f]
    assert len(stale) == 2, stale
    for line in stale:
        assert any(f"[{label}]" in line for label in labels), line


# ── each market is graded on its OWN exchange calendar ─────────────────────
def test_asia_boards_ahead_of_the_us_board_are_healthy():
    """HKEX and the mainland close hours BEFORE the ET nightly fires, so on 2026-08-04
    hk/cn read 2026-08-04 while us read 2026-07-31. Graded against one shared NYSE
    anchor, that healthy state reads as an anomaly in one direction and hides a real
    freeze in the other."""
    now = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
    report = evaluate([_run(created_at="2026-08-04T22:30:00Z")],
                      {"source_asof": "2026-08-04"}, now,
                      boards={"us": {"as_of": "2026-08-04"},
                              "cn": {"as_of": "2026-08-04"},
                              "hk": {"as_of": "2026-08-04"},
                              "ca": {"as_of": "2026-08-04"},
                              "intl": {"as_of": "2026-08-04"}})
    assert report["ok"] is True
    for market in ("us", "cn", "hk", "ca"):
        assert report["facts"]["boards"][market]["behind"] == 0, market


def test_one_session_behind_is_the_healthy_afternoon_shape():
    """At the 14:00Z slot the HK and mainland calendars have already rolled to today
    while today's bake does not fire until 22:30Z, so a healthy Asian board reads exactly
    one session behind every weekday afternoon. A budget of 0 would page five times a
    week — the false-positive factory this guard's own discipline forbids."""
    afternoon = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    report = evaluate([_run(created_at="2026-08-14T22:30:00Z")],
                      {"source_asof": "2026-08-14"}, afternoon,
                      boards={"us": {"as_of": "2026-08-14"},
                              "cn": {"as_of": "2026-08-14"},
                              "hk": {"as_of": "2026-08-14"},
                              "ca": {"as_of": "2026-08-14"},
                              "intl": {"as_of": "2026-08-14"}})
    assert report["facts"]["boards"]["hk"]["behind"] == 1
    assert report["ok"] is True


def test_a_market_holiday_cannot_manufacture_a_board_breach():
    """Victoria Day 2026-05-18 is a TSX closure and an ordinary NYSE session. A Canadian
    board holding Friday 05-15 is current, not stale, and the calendar is the only thing
    that knows that."""
    holiday_monday = datetime(2026, 5, 18, 13, 0, tzinfo=timezone.utc)
    report = evaluate([_run(created_at="2026-05-15T22:30:00Z")],
                      {"source_asof": "2026-05-15"}, holiday_monday,
                      boards={"us": {"as_of": "2026-05-15"},
                              "cn": {"as_of": "2026-05-15"},
                              "hk": {"as_of": "2026-05-15"},
                              "ca": {"as_of": "2026-05-15"},
                              "intl": {"as_of": "2026-05-15"}})
    assert report["ok"] is True
    assert report["facts"]["boards"]["ca"]["behind"] == 0


# Golden Week 2026 is Oct 1-7. A mainland board stamped 2026-09-28 reads 3 sessions
# behind on 10-09 purely because lib/cn_calendar's table is deliberately minimal and the
# State Council routinely runs the closure longer than the statutory core it encodes.
GW_NOW = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)
GW_RUNS = [_run(created_at="2026-10-08T22:30:00Z")]
GW_INDEX = {"source_asof": "2026-10-08"}


def _gw_boards(**overrides):
    base = {m: {"as_of": "2026-10-08"} for m in ("us", "cn", "hk", "ca", "intl")}
    return {**base, **overrides}


def test_mainland_holiday_floor_suppresses_inside_a_closure_window():
    """Those un-encoded days are phantom sessions, so the mainland alone carries a
    calendar-day floor. 11 days old with Golden Week in the gap is a holiday shape."""
    report = evaluate(GW_RUNS, GW_INDEX, GW_NOW,
                      boards=_gw_boards(cn={"as_of": "2026-09-28"}))
    assert report["facts"]["boards"]["cn"]["behind"] == 3
    assert report["ok"] is True
    assert any("longest-legitimate-closure floor" in w and "[China]" in w
               for w in report["warnings"]), report["warnings"]


def test_the_mainland_floor_expires_rather_than_blinding_forever():
    """A board past the floor is a proven freeze, not a holiday. The floor delays the
    page; it must never cancel it."""
    report = evaluate(GW_RUNS, GW_INDEX,
                      datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc),
                      boards=_gw_boards(cn={"as_of": "2026-09-28"}))
    assert report["ok"] is False
    assert any("STALE BOARD [China]" in f for f in report["fail_reasons"]), report


def test_the_mainland_floor_does_not_apply_outside_a_closure_window():
    """The narrowing. Phantom sessions can only accrue while the exchange is shut, so in
    August there is nothing for the floor to excuse and the mainland pages at 2 sessions
    like every other market. An always-on floor pushed this to 2026-08-26."""
    report = evaluate(D_RUNS, D_INDEX, D_NOW,
                      boards=_boards(cn={"as_of": "2026-08-13"},
                                     ca={"as_of": "2026-08-13"}))
    assert report["ok"] is False
    stale = [f for f in report["fail_reasons"] if "STALE BOARD" in f]
    assert {"[China]", "[Canada]"} == {t for t in ("[China]", "[Canada]")
                                       if any(t in f for f in stale)}, stale
    assert not any("longest-legitimate-closure floor" in w for w in report["warnings"])


def test_only_the_mainland_carries_a_calendar_day_floor():
    """Every other market's table is complete (or, for International, is an explicit
    approximation whose tolerance is priced into its budget instead). A floor elsewhere
    would be pure detection delay with no false-alarm to prevent."""
    floors = {s["market"]: s["min_calendar_days"] for s in MARKET_BOARDS}
    assert floors == {"us": None, "cn": 11, "hk": None, "ca": None, "intl": None}


# ── blindness discipline, per market ───────────────────────────────────────
@pytest.mark.parametrize("payload", [
    None,                      # artifact absent or unreadable
    {},                        # readable, no stamp field
    {"as_of": None},           # the live International shape
    {"as_of": "not-a-date"},   # unparseable
    {"as_of": ""},             # empty
])
def test_board_blindness_is_never_a_breach(payload):
    report = evaluate(D_RUNS, D_INDEX, D_NOW, boards=_boards(ca=payload))
    assert report["ok"] is True
    assert any("INDETERMINATE [Canada]" in w for w in report["warnings"]), report


def test_a_market_missing_from_the_payload_warns_rather_than_vanishing():
    """A forgotten sparse-checkout path looks exactly like this. It must not read green:
    an unwatched market is the failure this whole check exists for."""
    report = evaluate(D_RUNS, D_INDEX, D_NOW, boards={})
    assert report["ok"] is True
    blind = [w for w in report["warnings"] if "INDETERMINATE [" in w]
    assert len(blind) == len(MARKET_BOARDS), blind


def test_one_blind_market_leaves_the_others_graded():
    report = evaluate(D_RUNS, D_INDEX, D_NOW,
                      boards=_boards(us=None, ca={"as_of": "2026-08-13"}))
    assert report["ok"] is False
    assert any("STALE BOARD [Canada]" in f for f in report["fail_reasons"])
    assert any("INDETERMINATE [US]" in w for w in report["warnings"])


def test_check_d_is_silent_when_not_requested():
    """Every pre-D caller passes three positional arguments. They must keep working, and
    must not acquire a phantom five-market verdict from a default."""
    report = evaluate(D_RUNS, D_INDEX, D_NOW)
    assert report["ok"] is True
    assert "boards" not in report["facts"]


# ── registry + wiring: the ways this check can ship dead ───────────────────
def test_registry_covers_the_five_markets():
    assert [spec["market"] for spec in MARKET_BOARDS] == ["us", "cn", "hk", "ca", "intl"]
    paths = [spec["path"] for spec in MARKET_BOARDS]
    assert len(set(paths)) == len(paths), paths
    for spec in MARKET_BOARDS:
        assert spec["path"].startswith("site/"), spec
        assert spec["label"] and spec["field"], spec
        assert spec["max_sessions_behind"] >= 1, spec


def test_every_market_board_is_in_the_sparse_checkout():
    """THE wiring pin. A MARKET_BOARDS path missing from the workflow's sparse-checkout
    does not turn the lane red — the artifact is simply absent, that market degrades to
    INDETERMINATE, and the check exits 0. A forgotten line therefore ships a SILENTLY
    unwatched market, which is precisely the 2026-08-14 Canada failure re-created by the
    instrument built to catch it."""
    import yaml
    spec = yaml.safe_load(WORKFLOW.read_text())
    checkout = spec["jobs"]["liveness"]["steps"][0]["with"]["sparse-checkout"]
    listed = {line.strip() for line in checkout.splitlines() if line.strip()}
    for board in MARKET_BOARDS:
        assert board["path"] in listed, (
            f"{board['path']} is graded by check D but is not in the lane's "
            "sparse-checkout — that market would be silently ungraded"
        )


def test_main_grades_every_market(tmp_path, capsys):
    """Pins that main() actually LOADS the boards. evaluate() defaults ``boards=None``
    and is silent then, so a main() that forgot to pass them would leave check D fully
    dead while every unit test above still passed."""
    for board in MARKET_BOARDS:
        target = tmp_path / board["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({board["field"]: "2026-08-10"}))
    idx = tmp_path / "index.json"
    idx.write_text(json.dumps(FROZEN))
    runs = tmp_path / "runs.json"
    runs.write_text(json.dumps([]))

    rc = main(["--index-json", str(idx), "--runs-json", str(runs),
               "--site-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "market boards |" in out
    for board in MARKET_BOARDS:
        assert f"{board['market']}=2026-08-10" in out, out
    # Two of these fixtures are far enough behind to page; the point is only that main
    # reached them at all, and every annotation still starts the line.
    for line in out.splitlines():
        if "::error" in line or "::warning" in line:
            assert line.startswith("::"), line


def test_intl_board_is_a_known_blind_spot_today():
    """site/factordata/intl_setups.json has carried ``as_of: null`` on every commit in
    main's history — compute_intl_alpha stamps no as_of on any return path
    (scripts/build_intl_library.py, adversarial review D1, PR #5674). The guard reports
    that honestly rather than inventing a verdict.

    This test pins the CURRENT state deliberately: the day the builder starts stamping,
    this is what tells us International has become gradeable and the registry entry
    should be re-derived against a real calendar rather than the weekday approximation.
    """
    intl = next(s for s in MARKET_BOARDS if s["market"] == "intl")
    assert intl["calendar"] == "weekday"
    assert intl["max_sessions_behind"] == 3, (
        "the weekday approximation buys its +2 tolerance here; changing it needs the "
        "over-count argument in MARKET_BOARDS re-derived"
    )
    report = evaluate(D_RUNS, D_INDEX, D_NOW, boards=_boards(intl={"as_of": None}))
    assert report["ok"] is True
    assert any("INDETERMINATE [International]" in w for w in report["warnings"])
