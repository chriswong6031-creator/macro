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
    MAX_SESSIONS_BEHIND,
    WORKFLOW_FILE,
    evaluate,
    expected_fire_after,
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
    healthcheck's 96h. Check A is the only instrument that can see it."""
    report = evaluate([LAST_GOOD_RUN], FROZEN, NOW)
    assert report["ok"] is False
    assert any("NO RUN" in f for f in report["fail_reasons"])
    # If this ever reads > 1, the fixture has drifted and the test no longer pins
    # the "data checks are satisfied here" property that makes check A necessary.
    assert report["facts"]["sessions_behind"] == MAX_SESSIONS_BEHIND
    assert not any("STALE DATA" in f for f in report["fail_reasons"])


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
    of absence — check C is the backstop once the store falls far enough behind."""
    report = evaluate([_run(status="queued", conclusion=None)], FROZEN, NOW)
    assert report["ok"] is True
    assert report["warnings"]


def test_one_success_among_failures_is_healthy():
    """Reruns are normal; the night is fine if anything landed."""
    report = evaluate(
        [_run(conclusion="cancelled"), _run(conclusion="success")], ADVANCED, NOW)
    assert report["ok"] is True


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
