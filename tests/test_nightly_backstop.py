"""Pins the nightly backstop's dispatch rule.

The dangerous direction here is the opposite of a detector's. A detector that is
wrong raises a false alarm; an ACTOR that is wrong fires a production pipeline —
possibly on top of a live one, which is exactly the 2026-08-09 ci.yml livelock
where each re-dispatch killed the proof the whole fleet was waiting on. So most of
this suite is about the cases where it must do NOTHING.

Fixture dates are constants with no relation to the wall clock.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.nightly_backstop import (  # noqa: E402
    MAX_DISPATCHES,
    WORKFLOW_FILE,
    decide,
    fire_boundary,
)

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "nightly-backstop.yml"
PRIMARY = REPO_ROOT / ".github" / "workflows" / "daily.yml"

NOW = datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc)   # the 01:00Z slot


def _run(**kw):
    base = {"created_at": "2026-08-11T22:30:00Z", "status": "completed",
            "conclusion": "success", "event": "schedule"}
    base.update(kw)
    return base


LIVE = _run(status="in_progress", conclusion=None)
QUEUED = _run(status="queued", conclusion=None)
DEAD = _run(conclusion="cancelled")
LANDED = _run()
STALE = _run(created_at="2026-08-11T00:00:55Z")          # previous session's bake


# ── must NOT fire ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("runs,why", [
    ([LIVE], "in_progress"),
    ([QUEUED], "queued"),
    ([DEAD, LIVE], "a live run beside a dead one"),
    ([LANDED], "already succeeded"),
    ([DEAD, LANDED], "one failed, one succeeded"),
    (None, "blind — could not list runs"),
])
def test_does_not_dispatch(runs, why):
    assert decide(runs, NOW)["dispatch"] is False, why


def test_empty_list_and_blind_are_different_verdicts():
    """`[]` is a positive observation that no run exists — fire. `None` is a failed
    probe — do not. Collapsing the two either strands the night or dispatches on an
    unknown state, and both have happened to this repo."""
    assert decide([], NOW)["dispatch"] is True
    assert decide(None, NOW)["dispatch"] is False


def test_never_dispatches_over_a_live_run():
    """The 2026-08-09 livelock: main-ref dispatches shared one cancel-in-progress
    group, so each new dispatch KILLED the in-flight proof and the escape hatch was
    the lock. Tonight's bake also ran 2h+ in `collect` while perfectly healthy — a
    long job inside its timeout is not evidence that it is wedged."""
    verdict = decide([LIVE], NOW)
    assert verdict["dispatch"] is False
    assert "LIVE" in verdict["reason"]


def test_blindness_does_not_dispatch():
    """Opposite polarity from check_nightly_liveness.py: for a DETECTOR, blindness
    must not alarm; for an ACTOR, blindness must not act."""
    verdict = decide(None, NOW)
    assert verdict["dispatch"] is False
    assert "BLIND" in verdict["reason"]


# ── must fire ───────────────────────────────────────────────────────────────
def test_strand_dispatches():
    """No run since the boundary — the 2026-08-11 signature."""
    for runs in ([], [STALE]):
        verdict = decide(runs, NOW)
        assert verdict["dispatch"] is True, runs
        assert "NO RUN" in verdict["reason"]


def test_all_cancelled_dispatches():
    """The 2026-08-12 signature: every run force-cancelled, nothing alive."""
    verdict = decide([DEAD, DEAD], NOW)
    assert verdict["dispatch"] is True
    assert "ALL FAILED" in verdict["reason"]


# ── storm control ───────────────────────────────────────────────────────────
def test_dispatch_cap_holds():
    fired = _run(conclusion="failure", event="workflow_dispatch",
                 created_at="2026-08-11T23:00:00Z")
    assert decide([fired], NOW)["dispatch"] is True
    capped = decide([fired] * MAX_DISPATCHES, NOW)
    assert capped["dispatch"] is False
    assert "CAPPED" in capped["reason"]


def test_cap_counts_only_backstop_dispatches():
    """A night with many failed SCHEDULED runs is not a storm we caused; the cap is
    about our own re-fires."""
    many_scheduled = [_run(conclusion="failure") for _ in range(5)]
    assert decide(many_scheduled, NOW)["dispatch"] is True


# ── calendar anchoring ──────────────────────────────────────────────────────
def test_weekend_resolves_to_fridays_bake():
    sat = datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc)
    session, _ = fire_boundary(sat)
    assert session == "2026-08-14"
    friday = _run(created_at="2026-08-14T22:30:00Z")
    assert decide([friday], sat)["dispatch"] is False


def test_est_regime_run_after_utc_midnight_counts_as_tonights():
    """During EST the pair fires 23:30Z and dispatch lag pushes starts past 00:00Z.
    Misattributing those would re-fire a night that already ran."""
    assert decide([_run(created_at="2026-08-12T00:30:00Z")], NOW)["dispatch"] is False


# ── wiring ──────────────────────────────────────────────────────────────────
def test_workflow_is_off_the_pool_it_recovers():
    """A backstop that queues behind the outage it is recovering from is useless."""
    import yaml
    spec = yaml.safe_load(WORKFLOW.read_text())
    for job in spec["jobs"].values():
        runner = job.get("runs-on")
        labels = [runner] if isinstance(runner, str) else list(runner or [])
        assert labels == ["ubuntu-latest"], labels


def test_workflow_can_actually_dispatch():
    import yaml
    spec = yaml.safe_load(WORKFLOW.read_text())
    assert spec["permissions"]["actions"] == "write"
    assert "scripts/nightly_backstop.py" in WORKFLOW.read_text()


def test_backstop_never_cancels_its_own_slots():
    import yaml
    spec = yaml.safe_load(WORKFLOW.read_text())
    assert spec["concurrency"]["cancel-in-progress"] is False


def test_backstop_slots_sit_after_the_primary_fire():
    """Every backstop cron must land after the latest primary fire (23:30Z EST),
    i.e. in the small hours UTC — never before it, which would re-fire a night that
    has not been given its own chance yet."""
    import yaml
    spec = yaml.safe_load(WORKFLOW.read_text())
    # yaml parses the `on:` key as the boolean True.
    trigger = spec.get("on") or spec.get(True)
    crons = [c["cron"] for c in trigger["schedule"]]
    assert crons, trigger
    for cron in crons:
        minute, hour = cron.split()[0], cron.split()[1]
        assert 0 <= int(hour) < 8, f"{cron} is not in the post-bake window"
        int(minute)  # must parse


def test_primary_still_has_only_the_dst_pair():
    """If daily.yml ever grows its own backstop crons, this lane becomes duplicate
    firing and must be retired rather than left to double-run the pipeline."""
    import yaml
    spec = yaml.safe_load(PRIMARY.read_text())
    trigger = spec.get("on") or spec.get(True)
    crons = sorted(c["cron"] for c in trigger["schedule"])
    assert crons == ["30 22 * * *", "30 23 * * *"], crons


def test_targets_the_authoritative_build():
    assert WORKFLOW_FILE == "daily.yml"


def test_selftest_passes():
    proc = subprocess.run(
        [sys.executable, "scripts/nightly_backstop.py", "--selftest"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout
