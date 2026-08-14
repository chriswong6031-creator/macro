"""Tests for scripts/prophet_rescue.py — the Prophet US bounded self-heal lane.

WHAT THIS ENCODES.  On 2026-08-11 the US nightly did not run: #5362 pushed
daily.yml past GitHub's silent ~512,000-byte workflow-processing cap 57 minutes
before the 22:30Z cron.  On 2026-08-12 a fleet session force-cancelled six recovery
dispatches.  Prophet US served 2026-08-10 picks for two full sessions and the
operator found it by looking at the site.  Every sensor we owned scored it green:
``index.json.asof`` is ``date.today()`` at bake time, healthcheck.py is a 96-hour
instrument running on the host it watches, and a no-fire night creates no run
record for check_dead_cron to inspect.

Everything below tests ``decide()`` — the pure core — against synthetic snapshots.
No test may open a socket or read a clock: ``now`` is always an explicit constant.
Fixture dates are FROZEN LITERALS chosen from the real NYSE calendar, never derived
from today, so a passing suite cannot rot into a scheduled red.

THE FOUR SAFETY INVARIANTS (masterplan §0.4) are mutation-pinned.  Each has exactly
one test that is the sole thing standing between the guard and a live dispatch:

    §0.4a  never dispatch while a run is alive   -> test_a_live_run_blocks_the_dispatch
    §0.4b  never exceed the 2/night budget       -> test_budget_spent_downgrades_to_alert_only
    §0.4c  never cancel anything, ever           -> test_no_stop_run_code_path_exists
    §0.4d  a blind API read never dispatches     -> test_an_unreadable_run_list_never_dispatches

Run: python3 -m pytest tests/test_prophet_rescue.py -q
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "scripts" / "prophet_rescue.py"

_SPEC = importlib.util.spec_from_file_location("prophet_rescue_under_test", SCRIPT)
assert _SPEC and _SPEC.loader
RESCUE = importlib.util.module_from_spec(_SPEC)
sys.modules["prophet_rescue_under_test"] = RESCUE
_SPEC.loader.exec_module(RESCUE)


UTC = timezone.utc

# ── frozen calendar anchors (verified against lib.nyse_calendar) ─────────────
# 2026-08-12 Wed and 2026-08-13 Thu are ordinary sessions.
# 2026-08-14 Fri is a session; 08-15 Sat and 08-16 Sun are not.
# 2026-09-07 Mon is Labor Day (holiday); 2026-09-08 Tue is the session after it.
WED = date(2026, 8, 12)
THU = date(2026, 8, 13)
FRI = date(2026, 8, 14)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


def run_row(status: str = "completed", conclusion: str | None = "success", *,
            created: datetime, event: str = "schedule", run_id: int = 31753425298):
    return {
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event,
        "html_url": f"https://example.test/run/{run_id}",
    }


def index(*, source_asof: str, cohort_date: str | None = None, cohort_n: int = 25,
          eligible: int = 40, asof: str | None = None) -> dict:
    """A prophet index.json shaped like the real one (schema prophet.index/v1).

    ``asof`` defaults to a DIFFERENT, fresher date than ``source_asof`` on purpose:
    the top-level stamp is the publication clock and every fixture here must keep
    proving that reading it is the bug (build_prophet.py:2100).
    """
    stamp = cohort_date if cohort_date is not None else source_asof
    return {
        "schema": "prophet.index/v1",
        "asof": asof or "2026-08-14",
        "recorded_at": asof or "2026-08-14",
        "source_asof": source_asof,
        "gate_go": True,
        "plans": [
            {"id": f"P{i}", "recorded_at": stamp, "asset": "AAPL"}
            for i in range(cohort_n)
        ],
        "intake": {"eligible_after_skips": eligible, "originated": cohort_n},
    }


def state(**kw):
    """A snapshot that is HEALTHY unless a keyword pushes it off the happy path.

    ``now`` and ``session`` must be a MATCHED pair: a morning wake is owed the
    PREVIOUS session, because ``expected_last_session`` only counts a session as
    completed after 17:00 ET. The default pair is a Friday 08:40Z wake watching
    Thursday's bake; ``test_a_morning_wake_is_owed_the_previous_session`` pins that
    premise, because getting it wrong silently turns every fixture into a
    cohort-missing state that alarms for the wrong reason.
    """
    now = kw.pop("now", at(FRI, 8, 40))
    session = kw.pop("session", THU)          # what the calendar owes at `now`
    defaults = dict(
        main_index=index(source_asof=session.isoformat()),
        r2_index=index(source_asof=session.isoformat()),
        vps_status={"checks": {"site": {
            "commit_time": (now - timedelta(minutes=4)).isoformat()}}},
        runs=[run_row(created=at(session, 22, 31))],
        dispatch_runs_today=0,
    )
    defaults.update(kw)
    return RESCUE.WatchdogState(now=now, **defaults)


def verdicts(actions) -> list[str]:
    return [a.verdict for a in actions]


def kinds(actions) -> list[str]:
    return [a.kind for a in actions]


def dispatched(actions) -> bool:
    return any(a.kind == RESCUE.DISPATCH for a in actions)


def _module_ast() -> ast.Module:
    return ast.parse(SCRIPT.read_text(encoding="utf-8"))


def _docstrings(tree: ast.Module) -> set[str]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                out.add(doc)
    return out


def _url_templates() -> set[str]:
    """Every URL the module can build, f-string holes rendered as ``{expr}``.

    Whole f-strings are unparsed as one unit and their constant fragments are then
    skipped, so ``"https://…/repos/" + repo + "/issues"`` cannot smuggle an endpoint
    past the census as three innocuous pieces.
    """
    tree = _module_ast()
    docs = _docstrings(tree)
    joined = [n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)]
    inner = {id(sub) for j in joined for sub in ast.walk(j) if sub is not j}

    urls: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in inner:
            continue
        if isinstance(node, ast.JoinedStr):
            text = ast.unparse(node)
            text = text[2:-1] if text.startswith(("f'", 'f"')) else text
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in docs:
                continue
            text = node.value
        else:
            continue
        if text.startswith("http"):
            urls.add(text)
    return urls


# ─────────────────────────────────────────────────────────────────────────────
# calendar anchoring — §0.3
# ─────────────────────────────────────────────────────────────────────────────
def test_a_morning_wake_is_owed_the_previous_session():
    """The premise every fixture in this file rests on. At 08:40Z on Friday the
    Friday close has not happened, so the store is owed THURSDAY — and Thursday's
    bake fired at Thursday 22:30Z. Reading this off by one day turns a healthy
    snapshot into a cohort-missing alarm."""
    session, boundary = RESCUE.expected_fire_after(at(FRI, 8, 40))
    assert session == THU
    assert boundary == at(THU, 22, 0)
    # ...and the same wake one day earlier is owed Wednesday.
    assert RESCUE.expected_fire_after(at(THU, 8, 40))[0] == WED


def test_a_healthy_weekday_is_quiet_and_exits_zero():
    actions = RESCUE.decide(state())
    assert verdicts(actions) == [RESCUE.HEALTHY]
    assert RESCUE.exit_code(actions) == 0
    assert not dispatched(actions)


def test_saturday_and_sunday_are_quiet_after_a_friday_bake():
    """No weekday filter exists anywhere in the module — the NYSE calendar is the
    filter. On a weekend ``expected_last_session`` resolves to Friday, whose bake
    already happened, so a correct Saturday is indistinguishable from a correct
    Wednesday."""
    for day, hour in ((date(2026, 8, 15), 8), (date(2026, 8, 16), 13)):
        snapshot = state(
            now=at(day, hour), session=FRI,
            main_index=index(source_asof=FRI.isoformat()),
            r2_index=index(source_asof=FRI.isoformat()),
            runs=[run_row(created=at(FRI, 22, 33))],
        )
        actions = RESCUE.decide(snapshot)
        assert verdicts(actions) == [RESCUE.HEALTHY], f"{day} should be quiet"
        assert RESCUE.exit_code(actions) == 0


def test_the_tuesday_after_a_monday_holiday_expects_friday():
    """Labor Day 2026 = Mon 09-07. Tuesday morning is owed FRIDAY's data, not
    Monday's — a naive `yesterday` would page every holiday."""
    tuesday = date(2026, 9, 8)
    friday = date(2026, 9, 4)
    session, boundary = RESCUE.expected_fire_after(at(tuesday, 8, 40))
    assert session == friday
    assert boundary == at(friday, 22, 0)

    actions = RESCUE.decide(state(
        now=at(tuesday, 8, 40), session=friday,
        main_index=index(source_asof=friday.isoformat()),
        r2_index=index(source_asof=friday.isoformat()),
        runs=[run_row(created=at(friday, 22, 31))],
    ))
    assert verdicts(actions) == [RESCUE.HEALTHY]


# ─────────────────────────────────────────────────────────────────────────────
# §0.2 — freshness keys on source_asof + the cohort, NEVER on top-level asof
# ─────────────────────────────────────────────────────────────────────────────
def test_a_fresh_asof_over_a_three_session_stale_source_asof_alarms():
    """THE GATE (§0.2). ``asof`` says today; ``source_asof`` is three sessions back.

    This is the exact shape that served Aug-10 picks for two days while every
    instrument read green. A reader keying on ``asof`` scores this HEALTHY.
    """
    snapshot = state(
        now=at(THU, 9, 40), session=THU,
        main_index=index(source_asof="2026-08-10", asof=THU.isoformat()),
        r2_index=index(source_asof="2026-08-10"),
        runs=[run_row(status="completed", conclusion="failure",
                      created=at(WED, 23, 11))],
        dispatch_runs_today=0,
    )
    actions = RESCUE.decide(snapshot)
    assert RESCUE.STALE in verdicts(actions)
    assert RESCUE.exit_code(actions) != 0
    assert dispatched(actions), "a stale night past the completion deadline is re-armed"


def test_the_top_level_asof_is_never_read():
    """Mutation-shaped: rewriting ONLY ``asof`` must not change a single verdict."""
    stale = index(source_asof="2026-08-10", asof="2026-08-10")
    restamped = index(source_asof="2026-08-10", asof="2026-08-13")
    base = dict(now=at(THU, 9, 40), session=THU,
                r2_index=index(source_asof="2026-08-10"),
                runs=[run_row(conclusion="failure", created=at(WED, 23, 11))])
    assert (verdicts(RESCUE.decide(state(main_index=stale, **base)))
            == verdicts(RESCUE.decide(state(main_index=restamped, **base))))


def test_the_cohort_counts_per_plan_recorded_at_not_the_index_stamp():
    payload = index(source_asof=THU.isoformat(), cohort_date="2026-08-10",
                    cohort_n=25)
    assert RESCUE.cohort_size(payload, THU) == 0
    assert RESCUE.cohort_size(payload, date(2026, 8, 10)) == 25
    assert RESCUE.intake_eligible(payload) == 40


# ─────────────────────────────────────────────────────────────────────────────
# the deadline ladder
# ─────────────────────────────────────────────────────────────────────────────
def test_no_fire_is_not_a_strand_before_the_0140z_deadline():
    """The cron fires 22:30Z +27..90 min. Calling a no-fire night at 00:10Z would
    page on ordinary lateness — the false-positive factory that gets a watchdog
    muted, which is how you end up with no watchdog."""
    snapshot = state(
        now=at(FRI, 0, 10), session=THU,
        main_index=index(source_asof=WED.isoformat()),
        r2_index=index(source_asof=WED.isoformat()),
        runs=[],
    )
    actions = RESCUE.decide(snapshot)
    assert not dispatched(actions)
    assert RESCUE.STRAND not in verdicts(actions)
    assert RESCUE.exit_code(actions) == 0


def test_no_fire_becomes_a_strand_dispatch_at_0140z():
    """The 2026-08-11 signature: zero runs exist at all."""
    snapshot = state(
        now=at(FRI, 1, 40), session=THU,
        main_index=index(source_asof=WED.isoformat()),
        r2_index=index(source_asof=WED.isoformat()),
        runs=[],
    )
    actions = RESCUE.decide(snapshot)
    assert verdicts(actions) == [RESCUE.STRAND]
    assert dispatched(actions)
    assert RESCUE.exit_code(actions) != 0
    assert "512KB" in actions[0].message, "the receipt must name the #5362 class"


def test_stale_data_is_not_an_alarm_before_the_0940z_completion_deadline():
    """A bake that is merely running long is not a breach. At 05:40Z the store
    legitimately still reads the previous session."""
    snapshot = state(
        now=at(FRI, 5, 40), session=THU,
        main_index=index(source_asof=WED.isoformat()),
        r2_index=index(source_asof=WED.isoformat()),
        runs=[run_row(status="in_progress", conclusion=None,
                      created=at(THU, 22, 31))],
    )
    actions = RESCUE.decide(snapshot)
    assert verdicts(actions) == [RESCUE.WAIT]
    assert RESCUE.exit_code(actions) == 0


def test_past_the_1340z_floor_a_stale_night_alarms_without_dispatching():
    """A bake started here runs against mixed-vintage intraday data and the vintage
    gate refuses origination anyway — exactly what the 13-hour 2026-08-13 retry
    produced (publish green, zero plans). Recovery from here is an operator call."""
    snapshot = state(
        now=at(FRI, 13, 40), session=THU,
        main_index=index(source_asof=WED.isoformat()),
        r2_index=index(source_asof=WED.isoformat()),
        runs=[],
    )
    actions = RESCUE.decide(snapshot)
    assert verdicts(actions) == [RESCUE.STRAND]
    assert not dispatched(actions)
    assert actions[0].kind == RESCUE.ALERT
    assert actions[0].blocked_by == "past_floor"


def test_a_newest_cancelled_run_with_stale_data_is_re_armed():
    """The 2026-08-12 shape: a run existed and was killed. A kill and a no-fire leave
    the same trace in every DATA instrument, so only the run list can tell them
    apart — and either way the night is owed."""
    snapshot = state(
        now=at(FRI, 9, 40), session=THU,
        main_index=index(source_asof=WED.isoformat()),
        r2_index=index(source_asof=WED.isoformat()),
        runs=[run_row(status="completed", conclusion="cancelled",
                      created=at(THU, 23, 11))],
    )
    actions = RESCUE.decide(snapshot)
    assert verdicts(actions) == [RESCUE.STALE]
    assert dispatched(actions)
    assert "cancelled" in actions[0].message


# ─────────────────────────────────────────────────────────────────────────────
# §0.4a — MUTATION PIN: never dispatch while a run is alive
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("status", ["queued", "in_progress", "waiting", "requested"])
def test_a_live_run_blocks_the_dispatch(status):
    """MUTATION PIN §0.4a. Delete the ``in_flight is not None`` branch in
    ``_dispatch_blockers`` and this test goes red.

    The staleness conditions are fully met (past 09:40Z, store two sessions back,
    budget untouched, API readable) so the ONLY thing standing between this state
    and a dispatch is the live-run guard.
    """
    snapshot = state(
        now=at(FRI, 9, 40), session=THU,
        main_index=index(source_asof=WED.isoformat()),
        r2_index=index(source_asof=WED.isoformat()),
        runs=[run_row(status=status, conclusion=None, created=at(THU, 22, 31))],
        dispatch_runs_today=0,
    )
    actions = RESCUE.decide(snapshot)
    assert not dispatched(actions), f"a {status} run must never be piled onto"
    assert verdicts(actions) == [RESCUE.WAIT]
    assert actions[0].blocked_by == "run_in_flight"
    assert RESCUE.exit_code(actions) == 0, "a live bake is not an alarm"


def test_a_live_run_still_blocks_when_other_blockers_also_apply():
    """A live run is DOMINANT: past the floor and out of budget, it is still WAIT,
    because the subject is working and paging about it teaches the reader to
    ignore the channel."""
    snapshot = state(
        now=at(FRI, 13, 40), session=THU,
        main_index=index(source_asof=WED.isoformat()),
        r2_index=index(source_asof=WED.isoformat()),
        runs=[run_row(status="in_progress", conclusion=None, created=at(THU, 22, 31))],
        dispatch_runs_today=9,
    )
    actions = RESCUE.decide(snapshot)
    assert verdicts(actions) == [RESCUE.WAIT]
    assert not dispatched(actions)


# ─────────────────────────────────────────────────────────────────────────────
# §0.4b — MUTATION PIN: the auto-dispatch budget
# ─────────────────────────────────────────────────────────────────────────────
def test_budget_spent_downgrades_to_alert_only():
    """MUTATION PIN §0.4b. Delete the ``spent >= AUTO_DISPATCH_BUDGET`` branch in
    ``_dispatch_blockers`` and this test goes red.

    Counted across ALL actors: an operator recovering by hand spends the same
    allowance, because what is being protected is the runner pool and the ledger,
    not this lane's turn.
    """
    snapshot = state(
        now=at(FRI, 9, 40), session=THU,
        main_index=index(source_asof=WED.isoformat()),
        r2_index=index(source_asof=WED.isoformat()),
        runs=[run_row(conclusion="failure", created=at(THU, 23, 11))],
        dispatch_runs_today=RESCUE.AUTO_DISPATCH_BUDGET,
    )
    actions = RESCUE.decide(snapshot)
    assert not dispatched(actions)
    assert verdicts(actions) == [RESCUE.STALE]
    assert actions[0].kind == RESCUE.ALERT
    assert actions[0].blocked_by == "budget_spent"
    assert RESCUE.exit_code(actions) != 0, "out of budget IS a page"


def test_one_dispatch_short_of_the_budget_still_re_arms():
    """Control for the pin above — otherwise it could pass by never dispatching."""
    snapshot = state(
        now=at(FRI, 9, 40), session=THU,
        main_index=index(source_asof=WED.isoformat()),
        r2_index=index(source_asof=WED.isoformat()),
        runs=[run_row(conclusion="failure", created=at(THU, 23, 11))],
        dispatch_runs_today=RESCUE.AUTO_DISPATCH_BUDGET - 1,
    )
    assert dispatched(RESCUE.decide(snapshot))


def test_two_wakes_spend_one_budget_each_and_then_stop():
    """Idempotence over a night. Wake 1 re-arms; the dispatch it created is queued
    when wake 2 looks, so wake 2 waits; by wake 3 the budget is gone."""
    base = dict(session=THU,
                main_index=index(source_asof=WED.isoformat()),
                r2_index=index(source_asof=WED.isoformat()))
    wake1 = RESCUE.decide(state(
        now=at(FRI, 9, 40), runs=[run_row(conclusion="failure",
                                          created=at(THU, 23, 11))],
        dispatch_runs_today=0, **base))
    assert dispatched(wake1)

    wake2 = RESCUE.decide(state(
        now=at(FRI, 10, 40),
        runs=[run_row(status="queued", conclusion=None, created=at(FRI, 9, 41),
                      event="workflow_dispatch", run_id=1),
              run_row(conclusion="failure", created=at(THU, 23, 11))],
        dispatch_runs_today=1, **base))
    assert not dispatched(wake2)
    assert verdicts(wake2) == [RESCUE.WAIT]

    wake3 = RESCUE.decide(state(
        now=at(FRI, 12, 40),
        runs=[run_row(conclusion="failure", created=at(FRI, 9, 41),
                      event="workflow_dispatch", run_id=1),
              run_row(conclusion="failure", created=at(FRI, 10, 41),
                      event="workflow_dispatch", run_id=2),
              run_row(conclusion="failure", created=at(THU, 23, 11))],
        dispatch_runs_today=2, **base))
    assert not dispatched(wake3)
    assert wake3[0].blocked_by == "budget_spent"


# ─────────────────────────────────────────────────────────────────────────────
# §0.4c — MUTATION PIN: no way to stop a run exists in this module
# ─────────────────────────────────────────────────────────────────────────────
def test_no_stop_run_code_path_exists():
    """MUTATION PIN §0.4c. Add ANY run-stopping call to scripts/prophet_rescue.py —
    a ``/cancel`` or ``/force-cancel`` URL, a ``gh run cancel`` subprocess, an
    identifier with ``cancel`` in its name — and this test goes red.

    Prose already forbade this and did not bind: on 2026-08-12 a live fleet session
    force-cancelled the US nightly's recovery dispatches six times (receipt: POST
    /actions/runs/31583415065/force-cancel). A responder that CAN stop a run will
    eventually stop one, and the loss is invisible to every staleness instrument we
    own, because a killed bake and a bake that never fired leave the same trace.

    Comments and docstrings are exempt — a guard that forbids writing ABOUT the trap
    stops the fix and the postmortem, which the sibling hook learned in production
    the first minute it was live.
    """
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)

    offenders: list[str] = []
    for node in ast.walk(tree):
        # 1. no identifier may name the capability
        if isinstance(node, ast.Name) and "cancel" in node.id.lower():
            offenders.append(f"name {node.id!r} (line {node.lineno})")
        if isinstance(node, ast.Attribute) and "cancel" in node.attr.lower():
            offenders.append(f"attribute .{node.attr} (line {node.lineno})")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and "cancel" in node.name.lower():
            offenders.append(f"function {node.name!r} (line {node.lineno})")
        # 2. no runtime string may carry the endpoint or the CLI spelling
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value not in docstrings:
            low = node.value.lower()
            if re.search(r"/(force-)?cancel|run\s+cancel|cancel\b", low):
                offenders.append(f"string {node.value[:60]!r} (line {node.lineno})")

    assert not offenders, (
        "scripts/prophet_rescue.py has grown a way to stop a production run: "
        + "; ".join(offenders)
        + ". §0.4c is absolute — killing a wedged run is an OPERATOR call."
    )


def test_the_only_pipeline_write_is_a_dispatch():
    """Companion to the pin above, from the other direction: enumerate EVERY URL
    this module can construct and assert the whole network surface is the intended
    one. A new endpoint of any kind reds this test — including a stop-run one, which
    the AST pin above would also catch, and including a paginated read, which is how
    the shared 5,000/hr REST pool was emptied on 2026-07-26."""
    surface = _url_templates()
    assert surface, "the URL census matched nothing — the extractor is broken"

    github = {u for u in surface if "api.github.com" in u}
    paths = {u.split("/repos/{repo}", 1)[1] for u in github}
    assert paths == {
        "/contents/site/prophet/index.json?ref=main",
        "/actions/workflows/{WORKFLOW_FILE}/runs?per_page={RUNS_PER_PAGE}",
        "/actions/workflows/{WORKFLOW_FILE}/runs"
        "?event=workflow_dispatch&per_page={RUNS_PER_PAGE}&created={created}",
        "/actions/workflows/{WORKFLOW_FILE}/dispatches",
        "/labels",
        "/issues?labels={urllib.parse.quote(ISSUE_LABEL)}&state=open&per_page=50",
        "/issues",
        "/issues/{number}/comments",
    }, f"the GitHub surface changed: {sorted(paths)}"

    writes = {p for p in paths if p.startswith("/actions/") and "?" not in p}
    assert writes == {"/actions/workflows/{WORKFLOW_FILE}/dispatches"}, (
        f"the only write to the pipeline may be a dispatch, saw {sorted(writes)}"
    )
    for url in surface:
        assert "cancel" not in url.lower(), f"a stop-run URL appeared: {url}"
        assert "&page=" not in url and "?page=" not in url, (
            f"pagination in {url} — one page per wake, always"
        )
    assert {u for u in surface if "api.github.com" not in u} == {
        RESCUE.R2_INDEX_URL,
        RESCUE.VPS_STATUS_URL,
        "https://api.telegram.org/bot{tg_token}/sendMessage",
    }, "an unexpected external host appeared"


# ─────────────────────────────────────────────────────────────────────────────
# §0.4d — MUTATION PIN: blind never dispatches
# ─────────────────────────────────────────────────────────────────────────────
def test_an_unreadable_run_list_never_dispatches():
    """MUTATION PIN §0.4d. Delete the ``state.runs is None`` half of the api_dark
    branch in ``_dispatch_blockers`` and this test goes red.

    The data side alone says the night is owed (source_asof two sessions back, past
    09:40Z), so the dispatch is WANTED — only the blindness guard stops it. Fail
    toward alerting; never toward blind re-arming.
    """
    snapshot = state(
        now=at(FRI, 9, 40), session=THU,
        main_index=index(source_asof=WED.isoformat()),
        r2_index=index(source_asof=WED.isoformat()),
        runs=None, runs_error="HTTP 403",
        dispatch_runs_today=0,
    )
    actions = RESCUE.decide(snapshot)
    assert not dispatched(actions)
    assert RESCUE.API_DARK in verdicts(actions)
    stale = [a for a in actions if a.verdict == RESCUE.STALE]
    assert stale and stale[0].kind == RESCUE.ALERT
    assert "api_dark" in (stale[0].blocked_by or "")
    assert RESCUE.exit_code(actions) != 0


def test_an_unreadable_budget_probe_never_dispatches():
    """The other half of §0.4d: the run list is fine, but we cannot count how many
    re-arms already exist. An uncounted budget is an unbounded one."""
    snapshot = state(
        now=at(FRI, 1, 40), session=THU,
        main_index=index(source_asof=WED.isoformat()),
        r2_index=index(source_asof=WED.isoformat()),
        runs=[],
        dispatch_runs_today=None, dispatch_probe_error="Timeout",
    )
    actions = RESCUE.decide(snapshot)
    assert not dispatched(actions)
    assert RESCUE.API_DARK in verdicts(actions)
    strand = [a for a in actions if a.verdict == RESCUE.STRAND]
    assert strand and strand[0].kind == RESCUE.ALERT


def test_an_unreadable_main_index_alarms_rather_than_scoring_green():
    snapshot = state(
        now=at(FRI, 8, 40), session=THU,
        main_index=None, main_error="HTTP 404",
        r2_index=None,
    )
    actions = RESCUE.decide(snapshot)
    assert verdicts(actions) == [RESCUE.API_DARK]
    assert RESCUE.exit_code(actions) != 0


# ─────────────────────────────────────────────────────────────────────────────
# the zero-origination wedge (alert-only)
# ─────────────────────────────────────────────────────────────────────────────
def test_a_fresh_store_with_no_cohort_and_eligible_candidates_is_no_cohort():
    """2026-08-13's shape: publish green, source_asof advanced, zero plans
    originated (`source_mixed_vintage: true`, `gate_go: false`). A re-dispatch
    cannot fix code, so this must alert and must NOT spend a bake."""
    snapshot = state(
        now=at(FRI, 9, 40), session=THU,
        main_index=index(source_asof=THU.isoformat(), cohort_date=WED.isoformat(),
                         cohort_n=25, eligible=40),
        r2_index=index(source_asof=THU.isoformat()),
        runs=[run_row(created=at(THU, 22, 31))],
    )
    actions = RESCUE.decide(snapshot)
    assert verdicts(actions) == [RESCUE.NO_COHORT]
    assert not dispatched(actions), "a code wedge is not a scheduling failure"
    assert RESCUE.exit_code(actions) != 0


def test_an_empty_cohort_with_zero_eligible_candidates_is_not_a_wedge():
    """A night where nothing qualified is a legitimate zero, not a defect. Alerting
    on it would make NO_COHORT mean nothing."""
    snapshot = state(
        now=at(FRI, 9, 40), session=THU,
        main_index=index(source_asof=THU.isoformat(), cohort_date=WED.isoformat(),
                         cohort_n=25, eligible=0),
        r2_index=index(source_asof=THU.isoformat()),
        runs=[run_row(created=at(THU, 22, 31))],
    )
    assert verdicts(RESCUE.decide(snapshot)) == [RESCUE.HEALTHY]


# ─────────────────────────────────────────────────────────────────────────────
# serve splits — main is the truth, the edges are what users read
# ─────────────────────────────────────────────────────────────────────────────
def test_a_stale_public_r2_mirror_is_a_serve_split():
    """The browser paints Prophet from the R2 public base, so main being right is
    not the same as the product being right."""
    snapshot = state(
        now=at(FRI, 8, 40), session=THU,
        main_index=index(source_asof=THU.isoformat()),
        r2_index=index(source_asof="2026-08-10"),
    )
    actions = RESCUE.decide(snapshot)
    assert verdicts(actions) == [RESCUE.SERVE_SPLIT_R2]
    assert not dispatched(actions)
    assert RESCUE.exit_code(actions) != 0


def test_an_r2_mirror_ahead_of_main_is_not_a_split():
    """R2 can lead main mid-publish. Only R2 BEHIND main is a user-visible split."""
    snapshot = state(
        now=at(FRI, 8, 40), session=THU,
        main_index=index(source_asof="2026-08-12"),
        r2_index=index(source_asof=THU.isoformat()),
    )
    assert RESCUE.SERVE_SPLIT_R2 not in verdicts(RESCUE.decide(snapshot))


def test_an_unreachable_r2_is_not_reported_as_a_split():
    """Blind is not a breach — the R2 fetch failing must not manufacture a verdict."""
    snapshot = state(now=at(FRI, 8, 40), session=THU,
                     r2_index=None, r2_error="HTTP 522")
    assert verdicts(RESCUE.decide(snapshot)) == [RESCUE.HEALTHY]


def test_a_stalled_vps_pull_loop_is_a_serve_split():
    """The VPS pulls main every 3 minutes. 45 minutes behind is fifteen missed
    pulls: everything merged since then is invisible to logged-in users."""
    now = at(FRI, 8, 40)
    snapshot = state(
        now=now, session=THU,
        vps_status={"checks": {"site": {
            "commit_time": (now - timedelta(minutes=45)).isoformat()}}},
    )
    actions = RESCUE.decide(snapshot)
    assert verdicts(actions) == [RESCUE.SERVE_SPLIT_VPS]
    assert RESCUE.exit_code(actions) != 0


@pytest.mark.parametrize("payload", [None, {}, {"checks": {}},
                                     {"checks": {"site": {"commit_time": None}}},
                                     {"checks": {"site": {"commit_time": "garbage"}}}])
def test_an_unreadable_vps_status_is_blind_not_a_breach(payload):
    snapshot = state(now=at(FRI, 8, 40), session=THU, vps_status=payload)
    assert verdicts(RESCUE.decide(snapshot)) == [RESCUE.HEALTHY]


# ─────────────────────────────────────────────────────────────────────────────
# host lane
# ─────────────────────────────────────────────────────────────────────────────
def test_the_launchd_lane_alarms_on_low_disk_and_the_actions_lane_ignores_it():
    """actions-runner-2 hit 'No space left on device' at 14:29Z on 2026-08-13 and
    took two jobs of the recovery bake with it, reported as unrelated failures.
    Only the host lane can see this; the hosted lane must not invent it."""
    host = RESCUE.decide(state(now=at(FRI, 8, 40), session=THU,
                               lane="launchd", disk_free_gb=12.0))
    assert RESCUE.DISK_LOW in verdicts(host)
    assert RESCUE.exit_code(host) != 0

    healthy_host = RESCUE.decide(state(now=at(FRI, 8, 40), session=THU,
                                       lane="launchd", disk_free_gb=310.0))
    assert verdicts(healthy_host) == [RESCUE.HEALTHY]

    hosted = RESCUE.decide(state(now=at(FRI, 8, 40), session=THU,
                                 lane="actions", disk_free_gb=12.0))
    assert RESCUE.DISK_LOW not in verdicts(hosted)


# ─────────────────────────────────────────────────────────────────────────────
# purity + house laws
# ─────────────────────────────────────────────────────────────────────────────
def test_decide_reads_no_clock_and_opens_no_socket():
    """``decide`` is pure by construction, so the test matrix above is the whole
    contract. Anything that reaches for ``datetime.now`` or ``urlopen`` inside it
    makes a fixture's verdict depend on the day CI happened to run."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "decide")
    called: list[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute):
                called.append(target.attr)
            elif isinstance(target, ast.Name):
                called.append(target.id)
    forbidden = {"now", "utcnow", "today", "urlopen", "Request", "run", "read_text",
                 "open"}
    assert not forbidden & set(called), (
        f"decide() reached for {sorted(forbidden & set(called))} — the core must "
        "stay pure or the fixtures below stop meaning anything"
    )


def test_every_annotation_starts_its_line_and_flushes():
    """House law (tests/test_gh_annotation_line_start.py): GitHub parses a workflow
    command only when ``::`` is the first thing on the line, and every logger here
    prefixes its format, so ``log.error("::error …")`` emits ``ERROR ::error …`` and
    is silently dropped. That shipped dead five times before the guard existed."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        head = node.args[0]
        literal = None
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            literal = head.value
        elif isinstance(head, ast.JoinedStr) and head.values:
            first = head.values[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                literal = first.value
        if literal is None or not literal.startswith("::"):
            continue
        assert isinstance(node.func, ast.Name) and node.func.id == "print", (
            f"line {node.lineno}: an annotation must be a bare print(), never a "
            "logger call — a prefixing format silently eats it"
        )
        assert any(kw.arg == "flush" and getattr(kw.value, "value", None) is True
                   for kw in node.keywords), (
            f"line {node.lineno}: annotations need flush=True — stdout is "
            "block-buffered when piped in CI"
        )


def test_the_module_imports_only_stdlib_plus_the_nyse_calendar():
    """Independence is the whole point of this lane: it must run from a bare
    ``python3`` with no venv, and it must survive a repo whose engine tree does not
    import (the 2026-08-11 failure was a single file crossing a size cap)."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    first_party = roots & {"lib", "engine", "scripts", "app", "collectors", "admin"}
    assert first_party == {"lib"}, f"non-stdlib imports beyond lib: {first_party}"
    from_lib = {n.module for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("lib")}
    assert from_lib == {"lib.nyse_calendar"}, from_lib


def test_no_third_calendar_is_implemented_here():
    """§0.3 — expected-session maths comes from lib.nyse_calendar. A local holiday
    table is how healthcheck ended up with a divergent ``_sessions_stale``."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "expected_last_session" in source and "sessions_behind" in source
    for banned in ("Thanksgiving", "Juneteenth", "def holidays", "def is_session"):
        assert banned not in source, f"a second calendar is growing here: {banned}"


def test_the_rest_budget_of_a_healthy_wake_is_three_github_reads():
    """One shared 5,000/hr account bucket for the entire fleet, and this lane wakes
    hourly forever. Pagination is what emptied the pool on 2026-07-26."""
    source = SCRIPT.read_text(encoding="utf-8")
    reads = re.findall(r"https://api\.github\.com/repos/\{repo\}/[a-z]+", source)
    assert "per_page" in source and "--paginate" not in source
    assert source.count("_get_json(url, _api_headers(token))") \
        + source.count("_get_json(url, headers)") == 4, (
        "fetch layer grew a call: index + runs + budget + issue-lookup is the whole "
        f"read surface (saw {reads})"
    )


def test_the_public_r2_base_matches_the_configured_data_plane():
    """The hardcoded base must stay byte-equal to config.yml r2_data_plane.public_base
    — the module cannot read YAML (stdlib-only), so this test is the join."""
    config_text = (ROOT / "config.yml").read_text(encoding="utf-8")
    assert 'public_base: "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"' \
        in config_text
    assert RESCUE.R2_INDEX_URL == (
        "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/prophet/index.json"
    )


def test_the_repo_slug_matches_the_git_remote():
    """A typo here makes the lane permanently blind — it 404s into API_DARK forever
    and nobody reads a watchdog that is always yellow."""
    assert "mastermindx-market-intelligence/macro" in RESCUE.DEFAULT_REPO


def test_the_workflow_it_dispatches_is_the_authoritative_nightly():
    """closing-bell.yml ran green on both outage nights while the board it rendered
    still read price_through=2026-08-10. Build A is not a substitute for Build B."""
    assert RESCUE.WORKFLOW_FILE == "daily.yml"
    assert (ROOT / ".github" / "workflows" / "daily.yml").exists()
