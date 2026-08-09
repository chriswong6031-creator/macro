"""ET regime gate for daily.yml's DST cron pair (Nov-2026 FINRA race fix).

The nightly anchors at 18:30 America/New_York year-round, ~30 min after the
~6pm-ET FINRA CNMSshvol post. GitHub cron has no timezone, so daily.yml ships a
DST PAIR ("30 22 * * *" for EDT, "30 23 * * *" for EST) and the root ``et_gate``
job keeps exactly one of them: it derives the New York UTC offset from stdlib
``zoneinfo`` and compares the fired ``github.event.schedule`` against the cron
the current regime intends. Without the gate, the November flip turns 22:30Z
into 17:30 EST, which RACES the FINRA file — collectors/finra_short_volume.py
404-skips and self-heals the next night, so the site would run one day stale all
winter with nothing red.

Two halves:

1. BEHAVIOR — these tests EXTRACT the inline gate script out of daily.yml and
   EXECUTE it against fixed instants either side of both DST flips. A mirrored
   copy of the logic would be vacuous: it would pass while the shipped workflow
   drifted. Instants are timezone-AWARE, so the result does not depend on the
   machine's local TZ.

2. WIRING — the anti-drift pins: the yaml cron pair and the script's cron
   constants may only move in lockstep; EVERY job (present and future) must
   REACH the gate, either directly (``et_gate`` in ``needs`` + the guard in its
   ``if``) or transitively down a needs-chain, with the transitive set held as
   an explicit allowlist; ``et_gate`` stays ubuntu-hosted and checkout-free (a
   self-hosted job with a cap would owe the W2 timings wiring in
   tests/test_nightly_timings.py, and a checkout of the multi-GB tree would blow
   the ~15-second budget for the no-op firing); and the jobs that carry
   ``always()`` keep it — that is what makes the gate FAIL-OPEN.

Run (CI runs UTC — reproduce it exactly):
    TZ=UTC python -m pytest tests/test_daily_et_gate.py -q
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / ".github" / "workflows" / "daily.yml"

EDT_CRON = "30 22 * * *"
EST_CRON = "30 23 * * *"
GUARD = "needs.et_gate.outputs.run != 'false'"

HEREDOC_OPEN = "python3 - <<'PY'"
HEREDOC_CLOSE = "PY"


# ---------------------------------------------------------------------------
# extraction — the SHIPPED script, never a copy
# ---------------------------------------------------------------------------

def _workflow() -> dict:
    return yaml.safe_load(DAILY.read_text(encoding="utf-8"))


def _on_block(wf: dict) -> dict:
    # yaml.safe_load parses the bare ``on:`` key as the boolean True
    return wf.get(True) or wf["on"]


def _gate_step() -> dict:
    steps = _workflow()["jobs"]["et_gate"]["steps"]
    gate = [s for s in steps if s.get("id") == "gate"]
    assert len(gate) == 1, f"expected exactly one et_gate step with id 'gate', got {len(gate)}"
    return gate[0]


def _gate_source() -> str:
    """The inline python out of daily.yml, heredoc wrapper stripped."""
    lines = _gate_step()["run"].splitlines()
    assert lines[0].strip() == HEREDOC_OPEN, (
        f"et_gate step no longer opens with {HEREDOC_OPEN!r}: {lines[0]!r}"
    )
    body = lines[1:]
    while body and not body[-1].strip():
        body.pop()
    assert body and body[-1].strip() == HEREDOC_CLOSE, (
        f"et_gate heredoc no longer terminates with {HEREDOC_CLOSE!r}: {body[-1]!r}"
    )
    return textwrap.dedent("\n".join(body[:-1])) + "\n"


GATE_SRC = _gate_source()


def run_gate(event, fired, now_iso, tmp_path, monkeypatch, capsys):
    """Execute the shipped gate script; return (verdict, stdout)."""
    out_file = tmp_path / "github_output.txt"
    out_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("EVENT_NAME", event)
    monkeypatch.setenv("FIRED_CRON", fired)
    monkeypatch.setenv("ET_GATE_NOW_UTC", now_iso)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    exec(compile(GATE_SRC, "daily.yml::et_gate", "exec"), {"__name__": "__main__"})
    stdout = capsys.readouterr().out
    written = [
        line.split("=", 1)[1]
        for line in out_file.read_text(encoding="utf-8").splitlines()
        if line.startswith("run=")
    ]
    assert written, f"gate wrote no run= line to GITHUB_OUTPUT (stdout: {stdout!r})"
    return written[-1], stdout


# ---------------------------------------------------------------------------
# behavior — regime vectors
# ---------------------------------------------------------------------------

# (event, fired cron, aware-UTC instant, expected verdict)
REGIME_VECTORS = [
    # EDT, mid-summer: the 22:30Z line is the real one.
    ("schedule", EDT_CRON, "2026-07-15T22:30:00+00:00", "true"),
    ("schedule", EST_CRON, "2026-07-15T23:30:00+00:00", "false"),
    # EST, mid-November — THE DEFECT VECTOR. Pre-fix, 22:30Z was the only cron
    # and it fired at 17:30 EST, ahead of the FINRA post.
    ("schedule", EDT_CRON, "2026-11-15T22:30:00+00:00", "false"),
    ("schedule", EST_CRON, "2026-11-15T23:30:00+00:00", "true"),
    # Fall flip weekend (US DST ends 2026-11-01 06:00Z): Saturday is still EDT,
    # Sunday evening is already EST.
    ("schedule", EDT_CRON, "2026-10-31T22:30:00+00:00", "true"),
    ("schedule", EST_CRON, "2026-10-31T23:30:00+00:00", "false"),
    ("schedule", EDT_CRON, "2026-11-01T22:30:00+00:00", "false"),
    ("schedule", EST_CRON, "2026-11-01T23:30:00+00:00", "true"),
    # Spring flip (US DST starts 2027-03-14 07:00Z).
    ("schedule", EST_CRON, "2027-03-13T23:30:00+00:00", "true"),
    ("schedule", EDT_CRON, "2027-03-15T22:30:00+00:00", "true"),
    ("schedule", EST_CRON, "2027-03-15T23:30:00+00:00", "false"),
    # Delay tolerance: REGIME beats wall-clock. A real firing that sat queued
    # 5h behind a long run still proceeds — a wall-clock window check here would
    # silently skip the sole authoritative nightly.
    ("schedule", EDT_CRON, "2026-07-16T03:45:00+00:00", "true"),
    # Manual dispatch is never gated (the flip-weekend backstop).
    ("workflow_dispatch", "", "2026-11-15T22:30:00+00:00", "true"),
]


@pytest.mark.parametrize("event,fired,now_iso,expected", REGIME_VECTORS)
def test_gate_verdict_follows_the_ny_regime(event, fired, now_iso, expected,
                                            tmp_path, monkeypatch, capsys):
    verdict, stdout = run_gate(event, fired, now_iso, tmp_path, monkeypatch, capsys)
    assert verdict == expected, (
        f"event={event} fired={fired!r} at {now_iso}: expected run={expected}, "
        f"got run={verdict} (gate said: {stdout.strip()!r})"
    )


def test_november_defect_vector_is_the_one_that_flipped(tmp_path, monkeypatch, capsys):
    """Regression anchor: 22:30Z in November must NOT run (it is 17:30 EST,
    ahead of the FINRA CNMSshvol post), and 23:30Z must."""
    early, _ = run_gate("schedule", EDT_CRON, "2026-11-15T22:30:00+00:00",
                        tmp_path, monkeypatch, capsys)
    late, _ = run_gate("schedule", EST_CRON, "2026-11-15T23:30:00+00:00",
                       tmp_path, monkeypatch, capsys)
    assert (early, late) == ("false", "true")


def test_annotation_starts_the_line_exactly_once(tmp_path, monkeypatch, capsys):
    """GitHub parses ``::`` only at column 0 — a prefixed line ships a dead alarm."""
    _, stdout = run_gate("schedule", EDT_CRON, "2026-07-15T22:30:00+00:00",
                         tmp_path, monkeypatch, capsys)
    notices = [l for l in stdout.splitlines() if l.startswith("::notice")]
    assert len(notices) == 1, f"expected exactly one line-start ::notice, got: {stdout!r}"
    assert notices[0].startswith("::notice title=daily ET gate::")
    assert "run=true" in notices[0]


# ---------------------------------------------------------------------------
# wiring — daily.yml anti-drift pins
# ---------------------------------------------------------------------------

def test_cron_pair_and_script_constants_move_in_lockstep():
    crons = [s["cron"] for s in _on_block(_workflow())["schedule"]]
    assert crons == [EDT_CRON, EST_CRON], (
        f"daily.yml schedule is {crons} — the 18:30-ET anchor needs exactly the DST pair"
    )
    for cron in crons:
        assert cron in GATE_SRC, (
            f"cron {cron!r} is scheduled but absent from the et_gate script — the gate "
            "would never match it and that firing would be dropped every night"
        )


# A job reaches the gate one of two ways. DIRECT: et_gate in needs + the guard in
# its if. TRANSITIVE: it has no status function in its if, so GitHub's implicit
# success() skips it whenever a gated need skips — which is exactly what an
# off-regime firing does to `collect`. The transitive pair is an ALLOWLIST because
# each one is a deliberate ruling, not a default; both keep their own fences:
#   capital_structure             — carries no `if:` at all (DNR:KILL-NIGHTLY-HARD-GATE,
#                                   tests/test_daily_capital_structure_job.py)
#   government_revenue_projection — `needs: collect` must stay a SCALAR
#                                   (tests/test_dag_conformance.py)
# Wiring either one directly would break those pins AND invent a failure mode: a
# gate ERROR fails OPEN into collect, so a directly-gated lane would be the one
# job that skipped the night.
TRANSITIVELY_GATED = {"capital_structure", "government_revenue_projection"}

# Any of these in an `if:` replaces the implicit success() and severs the skip
# propagation a transitively-gated job depends on. (`!cancelled()` matches too.)
STATUS_FUNCTIONS = ("always(", "cancelled(", "failure(")


def _needs_of(spec) -> list[str]:
    needs = spec.get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


def _gate_reach(jobs: dict) -> dict[str, str]:
    """Classify every job as 'root', 'direct', 'transitive', or 'UNGATED: <why>'."""
    reach: dict[str, str] = {"et_gate": "root"}

    def resolve(name: str, stack: frozenset) -> str:
        if name in reach:
            return reach[name]
        if name in stack:
            reach[name] = "UNGATED: needs cycle"
            return reach[name]
        spec = jobs[name]
        needs = _needs_of(spec)
        cond = str(spec.get("if") or "")
        severed = [f for f in STATUS_FUNCTIONS if f in cond]
        gated_needs = [
            n for n in needs
            if resolve(n, stack | {name}) in ("direct", "transitive")
        ]
        if "et_gate" in needs and GUARD in cond:
            reach[name] = "direct"
        elif severed:
            reach[name] = (
                f"UNGATED: not directly gated, and if={cond!r} uses {severed[0]}) "
                "which severs skip propagation"
            )
        elif gated_needs:
            reach[name] = "transitive"
        else:
            reach[name] = (
                f"UNGATED: needs={needs} reaches no gated job and if={cond!r} "
                "carries no gate"
            )
        return reach[name]

    for key in jobs:
        resolve(key, frozenset())
    return reach


def test_every_job_reaches_the_et_gate():
    """Anti-drift for jobs added later: a new job that forgets the gate would run
    twice a day forever (once off-regime), which is how the pair pays for itself."""
    jobs = _workflow()["jobs"]
    assert "et_gate" in jobs, "the root ET gate job is gone"
    reach = _gate_reach(jobs)
    ungated = {k: v for k, v in reach.items() if v.startswith("UNGATED")}
    assert not ungated, (
        "daily.yml job(s) do not reach the ET regime gate — an off-regime firing "
        f"would run them. Wire et_gate into needs and add `{GUARD}` to the if "
        "(or keep the if free of status functions so a skipped need propagates):\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(ungated.items()))
    )


def test_the_transitively_gated_jobs_are_an_explicit_allowlist():
    """Transitive gating is a ruling per job, never a default a new job drifts into."""
    reach = _gate_reach(_workflow()["jobs"])
    actual = {k for k, v in reach.items() if v == "transitive"}
    assert actual == TRANSITIVELY_GATED, (
        f"transitively-gated jobs are {sorted(actual)}, allowlist is "
        f"{sorted(TRANSITIVELY_GATED)}. A job reaching the gate only through a "
        "needs-chain is a deliberate call (it exists here because a direct wire "
        "would break that lane's own fences) — wire the new job directly, or add "
        "it to TRANSITIVELY_GATED with the reason."
    )


def test_gate_job_stays_cheap_and_uninstrumented():
    """ubuntu-hosted + checkout-free: the off-regime firing must cost ~15 seconds,
    and a self-hosted job with timeout-minutes would owe the W2 timings steps
    (tests/test_nightly_timings.py's instrumentation predicate)."""
    spec = _workflow()["jobs"]["et_gate"]
    assert spec["runs-on"] == "ubuntu-latest", (
        f"et_gate runs-on={spec['runs-on']!r} — it must stay off the macstudio pool "
        "and outside the self-hosted timings predicate"
    )
    for step in spec["steps"]:
        uses = step.get("uses") or ""
        assert "actions/checkout" not in uses, (
            "et_gate must not check the repo out — the clone is multi-GB and this job "
            "exists to be nearly free"
        )
        assert "timings" not in (step.get("name") or ""), step


def test_fail_open_jobs_keep_their_always():
    """`always() &&` is what makes the gate fail-OPEN: an errored gate job must
    double-run the night, never silently zero-run it."""
    jobs = _workflow()["jobs"]
    for key in ("collect", "engine", "publish"):
        assert "always() &&" in str(jobs[key].get("if")), (
            f"{key}: if={jobs[key].get('if')!r} lost its always() — an et_gate error "
            "would now skip it via needs-status and kill the nightly silently"
        )
