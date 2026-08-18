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

import ast
import json
import textwrap
from datetime import datetime, timedelta, timezone
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


# ---------------------------------------------------------------------------
# extraction — the SHIPPED mutex step (2026-08-18 double-collect fix)
# ---------------------------------------------------------------------------
#
# ``gate`` disambiguates the DST cron pair; ``mutex`` closes a separate gap —
# the concurrency: block deliberately puts each DST cron and every
# workflow_dispatch in its OWN group (the 2026-08-14/15 pending-supersede
# kill), so nothing there stops two of those groups from running `collect`
# concurrently. 2026-08-18: exactly that happened (run 32077948964 and run
# 32084697588 both committed "data: daily collection 2026-08-18" ~20 minutes
# apart) and produced two independent fleet-blocking main reds. ``mutex`` asks
# the Actions API whether another daily.yml run is already live before
# `collect` is allowed to start.

def _mutex_step() -> dict:
    steps = _workflow()["jobs"]["et_gate"]["steps"]
    mutex = [s for s in steps if s.get("id") == "mutex"]
    assert len(mutex) == 1, f"expected exactly one et_gate step with id 'mutex', got {len(mutex)}"
    return mutex[0]


def _heredoc_body(step: dict) -> str:
    """Strip a step's ``python3 - <<'PY' ... PY`` heredoc wrapper and dedent.

    Shared shape with ``_gate_source``'s inline logic above — kept as a
    separate function (rather than refactoring ``_gate_source`` to call it)
    so a change here can never alter what the already-passing gate tests
    extract and execute.
    """
    lines = step["run"].splitlines()
    assert lines[0].strip() == HEREDOC_OPEN, (
        f"{step.get('id')} step no longer opens with {HEREDOC_OPEN!r}: {lines[0]!r}"
    )
    body = lines[1:]
    while body and not body[-1].strip():
        body.pop()
    assert body and body[-1].strip() == HEREDOC_CLOSE, (
        f"{step.get('id')} heredoc no longer terminates with {HEREDOC_CLOSE!r}: {body[-1]!r}"
    )
    return textwrap.dedent("\n".join(body[:-1])) + "\n"


def _mutex_source() -> str:
    """The inline python out of daily.yml's mutex step, heredoc stripped."""
    return _heredoc_body(_mutex_step())


MUTEX_SRC = _mutex_source()

MUTEX_ALLOWED_IMPORT_ROOTS = {"json", "os", "urllib", "datetime"}


class _FakeHTTPResponse:
    """Minimal stand-in for ``http.client.HTTPResponse`` as a context manager."""

    def __init__(self, payload: dict, status: int = 200):
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _urlopen_router(routes: dict[str, dict]):
    """Fake ``urllib.request.urlopen`` matching a request's URL by substring."""

    def _urlopen(req, timeout=None):  # noqa: ARG001 - must match urlopen's signature
        url = req.full_url
        for needle, payload in routes.items():
            if needle in url:
                return _FakeHTTPResponse(payload)
        raise AssertionError(f"unexpected URL in mutex test stub: {url}")

    return _urlopen


def _urlopen_raises(exc: Exception):
    def _urlopen(req, timeout=None):  # noqa: ARG001
        raise exc

    return _urlopen


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_mutex(tmp_path, monkeypatch, capsys, *, this_run_id: str, repo: str = "acme/example"):
    """Execute the shipped mutex script; return (verdict, stdout).

    Caller monkeypatches ``urllib.request.urlopen`` BEFORE calling this, same
    ordering ``run_gate`` uses for ``ET_GATE_NOW_UTC``.
    """
    out_file = tmp_path / "github_output.txt"
    out_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("REPO", repo)
    monkeypatch.setenv("THIS_RUN_ID", this_run_id)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    exec(compile(MUTEX_SRC, "daily.yml::et_gate::mutex", "exec"), {"__name__": "__main__"})
    stdout = capsys.readouterr().out
    written = [
        line.split("=", 1)[1]
        for line in out_file.read_text(encoding="utf-8").splitlines()
        if line.startswith("run=")
    ]
    assert written, f"mutex wrote no run= line to GITHUB_OUTPUT (stdout: {stdout!r})"
    return written[-1], stdout


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

def test_dst_cron_slots_do_not_share_a_concurrency_group():
    """2026-08-14/15: shared group + pending-supersede cancelled the EDT nightly.

    GitHub still replaces the one PENDING run in a concurrency group even when
    ``cancel-in-progress`` is false (fences.yml 2026-08-09). Distinct groups are
    the only lever that stops a gate-skip slot from eating a queued real slot.
    Event-conditional cancel-in-progress cannot: the killed run was queued, not
    in progress. Pin the shipped expression, then evaluate it for both crons.
    """
    conc = _workflow()["concurrency"]
    group_expr = conc["group"]
    assert conc["cancel-in-progress"] is False, (
        "cancel-in-progress must stay false — a second fire of the SAME slot "
        "must not kill a running bake"
    )
    assert "github.event.schedule" in group_expr, (
        "concurrency.group must key on the fired cron; a static group lets the "
        "EST-guard supersede a queued EDT nightly"
    )
    assert "format(" in group_expr

    def eval_group(event_name: str, schedule: str = "") -> str:
        """Tiny GitHub-expression subset for this one shipped line."""
        inner = group_expr.strip()
        if inner.startswith("${{") and inner.endswith("}}"):
            inner = inner[3:-2].strip()
        inner = inner.replace("github.event_name", repr(event_name))
        inner = inner.replace("github.event.schedule", repr(schedule))
        # GitHub expressions use JS-style && / ||; Python's and / or match
        # the same truthy-return semantics for this line.
        inner = inner.replace("&&", " and ").replace("||", " or ")

        def _format(template: str, *args: object) -> str:
            out = template
            for i, arg in enumerate(args):
                out = out.replace("{" + str(i) + "}", str(arg))
            return out

        return eval(inner, {"__builtins__": {}}, {"format": _format})  # noqa: S307

    edt = eval_group("schedule", EDT_CRON)
    est = eval_group("schedule", EST_CRON)
    manual = eval_group("workflow_dispatch")
    assert edt != est, (
        f"EDT cron and EST-guard share group {edt!r} — the 2026-08-14/15 kill"
    )
    assert edt != manual and est != manual, (
        "a workflow_dispatch must not share a cron group (it would supersede "
        "a queued real slot the same way the EST-guard did)"
    )
    assert "30 22" in edt and "30 23" in est
    run_name = _workflow().get("run-name") or ""
    assert "github.event.schedule" in run_name, (
        "run-name must embed the fired cron so watchdogs can tell a gate-skip "
        "from a real bake without a jobs API call"
    )


def test_watchdog_cron_constants_lockstep_with_daily_yml():
    """Rescue and liveness classify slots by these strings — they must match."""
    from scripts.check_nightly_liveness import (  # noqa: PLC0415
        EDT_CRON as LIVE_EDT,
        EST_CRON as LIVE_EST,
    )
    from scripts.prophet_rescue import (  # noqa: PLC0415
        EDT_CRON as RESCUE_EDT,
        EST_CRON as RESCUE_EST,
    )
    assert {LIVE_EDT, LIVE_EST, RESCUE_EDT, RESCUE_EST} == {EDT_CRON, EST_CRON}


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


def test_gate_step_selector_still_resolves_exactly_one_step():
    """Anti-drift: the mutex step's addition below `gate` must not create a
    second `id: gate` match or otherwise confuse the existing selector."""
    steps = _workflow()["jobs"]["et_gate"]["steps"]
    gate_steps = [s for s in steps if s.get("id") == "gate"]
    assert len(gate_steps) == 1


# ---------------------------------------------------------------------------
# mutex — wiring (2026-08-18 double-collect fix)
# ---------------------------------------------------------------------------

def test_et_gate_job_declares_actions_read_permission():
    """The workflow-level permissions: block grants contents/pages/id-token but
    not `actions`, which the mutex step's Actions API reads need."""
    perms = _workflow()["jobs"]["et_gate"].get("permissions") or {}
    assert perms.get("actions") == "read", (
        f"et_gate permissions={perms} — job-level `actions: read` is required "
        "for the mutex step's runs/jobs API reads"
    )


def test_mutex_step_is_gated_checkout_free_and_cleanly_named():
    step = _mutex_step()
    assert step.get("if") == "steps.gate.outputs.run == 'true'", (
        "mutex must only run when the ET regime gate already said 'true' — "
        f"got if={step.get('if')!r}"
    )
    assert step.get("uses") is None, "mutex must not use actions/checkout"
    assert "timings" not in (step.get("name") or ""), (
        "mutex step name must not contain 'timings' — "
        "test_gate_job_stays_cheap_and_uninstrumented iterates every et_gate step"
    )
    env = step.get("env") or {}
    assert env.get("GH_TOKEN") == "${{ github.token }}"
    assert env.get("REPO") == "${{ github.repository }}"
    assert env.get("THIS_RUN_ID") == "${{ github.run_id }}"


def test_outputs_run_can_only_be_downgraded_by_the_mutex():
    """The job output must reference both step outputs, and the mutex may only
    ever force 'false' — an empty (skipped/no-standdown) mutex output must
    fall through to whatever the ET regime gate decided."""
    expr = _workflow()["jobs"]["et_gate"]["outputs"]["run"]
    assert "steps.mutex.outputs.run" in expr
    assert "steps.gate.outputs.run" in expr

    def eval_expr(mutex_run: str, gate_run: str) -> str:
        inner = expr.strip()
        if inner.startswith("${{") and inner.endswith("}}"):
            inner = inner[3:-2].strip()
        inner = inner.replace("steps.mutex.outputs.run", repr(mutex_run))
        inner = inner.replace("steps.gate.outputs.run", repr(gate_run))
        inner = inner.replace("&&", " and ").replace("||", " or ")
        return eval(inner, {"__builtins__": {}}, {})  # noqa: S307

    assert eval_expr("false", "true") == "false", "a mutex standdown must win over a gate 'true'"
    assert eval_expr("", "true") == "true", "a skipped mutex must fall through to the gate value"
    assert eval_expr("", "false") == "false", "gate already said no; mutex never even ran"
    assert eval_expr("true", "false") == "false", (
        "mutex can never UPGRADE past a gate 'false' (mutex only runs when gate "
        "already said 'true', so this combination cannot occur in practice, but "
        "the expression itself must not grant mutex that power)"
    )


def test_mutex_script_compiles_and_imports_only_stdlib():
    """et_gate is ubuntu-latest with no pip-install step — a non-stdlib import
    would fail at runtime, silently defeating the fail-open contract only if
    the import itself were wrapped in the try/except (it is NOT: imports sit
    at module top, so a bad import would hard-crash the step instead)."""
    compile(MUTEX_SRC, "daily.yml::et_gate::mutex", "exec")
    tree = ast.parse(MUTEX_SRC)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots, "mutex script imports nothing — extraction likely broke"
    assert roots <= MUTEX_ALLOWED_IMPORT_ROOTS, (
        f"mutex script imports non-stdlib module(s) {roots - MUTEX_ALLOWED_IMPORT_ROOTS} — "
        "et_gate has no pip-install step"
    )


# ---------------------------------------------------------------------------
# mutex — behavior
# ---------------------------------------------------------------------------

def test_mutex_fails_open_on_api_error(tmp_path, monkeypatch, capsys):
    """Same fail-open contract as `gate` above it: an API outage must double-run
    a night, never silently zero-run one."""
    monkeypatch.setattr("urllib.request.urlopen", _urlopen_raises(OSError("network is down")))
    verdict, stdout = run_mutex(tmp_path, monkeypatch, capsys, this_run_id="500001")
    assert verdict == "true"
    warnings = [line for line in stdout.splitlines() if line.startswith("::warning")]
    assert warnings, f"expected a line-start ::warning on API failure, got: {stdout!r}"
    assert "daily collect mutex" in warnings[0]


def test_mutex_stands_down_for_a_live_older_run(tmp_path, monkeypatch, capsys):
    """A genuinely-running older run (in_progress job) must block — this is the
    2026-08-18 defect vector: a second daily.yml run started `collect` while
    an earlier run's `collect` was still in flight."""
    this_id, other_id = 500202, 500101
    now = datetime.now(timezone.utc)
    routes = {
        "actions/workflows/daily.yml/runs?per_page=30": {
            "workflow_runs": [
                {"id": this_id, "status": "in_progress", "created_at": _iso(now)},
                {
                    "id": other_id,
                    "status": "in_progress",
                    "created_at": _iso(now - timedelta(minutes=10)),
                    "html_url": f"https://github.com/acme/example/actions/runs/{other_id}",
                },
            ]
        },
        f"actions/runs/{other_id}/jobs": {
            "jobs": [
                {
                    "status": "in_progress",
                    "started_at": _iso(now - timedelta(minutes=9)),
                    "completed_at": None,
                },
            ]
        },
    }
    monkeypatch.setattr("urllib.request.urlopen", _urlopen_router(routes))
    verdict, stdout = run_mutex(tmp_path, monkeypatch, capsys, this_run_id=str(this_id))
    assert verdict == "false"
    warnings = [line for line in stdout.splitlines() if line.startswith("::warning")]
    assert warnings, f"expected a line-start ::warning on standdown, got: {stdout!r}"
    assert str(other_id) in warnings[0] and str(this_id) in warnings[0]


def test_mutex_escape_hatch_lets_a_wedged_run_through(tmp_path, monkeypatch, capsys):
    """Anti-regression pin for clause (d), the operator escape hatch: a run
    whose jobs are all completed or queued, with no job activity in the last
    180 minutes, must NOT block — this is exactly the shape of run
    31977372592, which held its cron group for 26 hours on an unschedulable
    `theta-m1` runner label with nothing ever executing. Simplifying clause
    (d) to "any non-completed run blocks" would permanently wedge a manual
    rescue dispatch behind a run like that."""
    this_id, other_id = 500402, 500301
    now = datetime.now(timezone.utc)
    routes = {
        "actions/workflows/daily.yml/runs?per_page=30": {
            "workflow_runs": [
                {"id": this_id, "status": "in_progress", "created_at": _iso(now)},
                {
                    "id": other_id,
                    "status": "queued",
                    "created_at": _iso(now - timedelta(hours=5)),
                    "html_url": f"https://github.com/acme/example/actions/runs/{other_id}",
                },
            ]
        },
        f"actions/runs/{other_id}/jobs": {
            "jobs": [
                {
                    "status": "completed",
                    "started_at": _iso(now - timedelta(hours=5)),
                    "completed_at": _iso(now - timedelta(hours=4, minutes=50)),
                },
                {"status": "queued", "started_at": None, "completed_at": None},
            ]
        },
    }
    monkeypatch.setattr("urllib.request.urlopen", _urlopen_router(routes))
    verdict, stdout = run_mutex(tmp_path, monkeypatch, capsys, this_run_id=str(this_id))
    assert verdict == "true", (
        "a wedged older run (no in_progress job, no activity in 180 minutes) "
        "must not block a rescue dispatch"
    )
    notices = [line for line in stdout.splitlines() if line.startswith("::notice")]
    assert notices, f"expected a proceed ::notice, got: {stdout!r}"
