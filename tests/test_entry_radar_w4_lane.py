"""tests/test_entry_radar_w4_lane.py — the W4 deploy lane: units, gate, arm, tap.

W4 design §3 (module map), §3b (census pins) and the operator plan in
research/live_entry_radar/W4_DEPLOY_PLAN.md.  The evaluator's own behaviour is
pinned by the sibling W4 suites; what this file pins is everything the DEPLOYMENT
adds — the wiring nobody exercises until an operator arms the lane, which is
exactly the wiring that rots unread.

  HOST UNITS     four capped oneshots (evaluator + pack builder) on the lowest
                 priority tier, sharing ONE cap set because they are one program;
                 timers that cover the ET session in both DST regimes without
                 re-implementing the window; Persistent=false everywhere, because
                 replaying a missed intraday pass evaluates a stale tape against a
                 live clock.
  WRITER RACE    the evaluator fires at :04/5, one minute behind Prophet's :03/5
                 and four behind the :00/5 snapshot publication it reads.  That
                 spacing is asserted by PARSING ALL THREE TIMERS, so a future edit
                 to any one of them that collides is caught here rather than by a
                 session reading last cycle's quotes.
  ARM GATE       go-live is an explicit OPERATOR act (ENTRY_RADAR_LIVE_ENABLE=1 in
                 /etc/macro-live.env), not a repo commit — the commissioning drew
                 the deployment boundary at activation.  The arm check sits OUTSIDE
                 the CHANGED trigger in both directions, because the rollback is
                 deleting an env line and that touches no repo file.
  BACKSTOP       entry-radar-live.yml self-disables while the VPS is primary, the
                 program kill switch is NOT bypassable by workflow_dispatch, and
                 the lane still commits nothing (LEDGER LAW G0.2).
  GATE           /live/entry_radar.json is absent from the Caddy public allowlist,
                 so it inherits the auth gate BY OMISSION.  Design §3b promises
                 zero Caddyfile edits; this is the tripwire that keeps the promise
                 true after the next boundary edit rather than at merge only.
  LIVENESS       one freshness-sentinel SURFACES entry, absent_ok, so a staged-not-
                 armed lane never pages — and an ARMED one that stops advancing
                 does.
  HOT-TAPE TAP   the W1-designated PR-4 integration point in scripts/hot_tape_radar,
                 carrying the LIVE QUOTE MERGE vintage (not `now`, not the ET date),
                 with the spool's real failure behaviour pinned by driving a sink
                 that fails.

CLOCK.  Every timestamp derives from NOW, never from datetime.now, so nothing here
becomes a scheduled red on a Tuesday.  Nothing in this file writes ``data/``, opens
a socket, or needs an omitted sparse tree.
"""
from __future__ import annotations

import configparser
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.freshness_sentinel as FS  # noqa: E402
from engine.entry_radar.spool import (  # noqa: E402
    NominationSpool,
    spool_hot_tape,
    tap_hot_tape_events,
)

#: 2026-08-14 is a Friday; 14:00Z is 10:00 ET — inside the RTH window.
NOW = datetime(2026, 8, 14, 14, 0, tzinfo=timezone.utc)

DEPLOY = ROOT / "app" / "deploy"
EVAL_SERVICE = DEPLOY / "macro-live-entry-radar.service"
EVAL_TIMER = DEPLOY / "macro-live-entry-radar.timer"
PACK_SERVICE = DEPLOY / "macro-entry-radar-pack.service"
PACK_TIMER = DEPLOY / "macro-entry-radar-pack.timer"
PROPHET_TIMER = DEPLOY / "macro-live-prophet.timer"
SNAPSHOT_TIMER = DEPLOY / "macro-live-snapshot.timer"
UNIT_FILES = (EVAL_SERVICE, EVAL_TIMER, PACK_SERVICE, PACK_TIMER)

UPDATE_SH = (DEPLOY / "update.sh").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "entry-radar-live.yml").read_text(
    encoding="utf-8")
HOT_TAPE_SRC = (ROOT / "scripts" / "hot_tape_radar.py").read_text(encoding="utf-8")

#: The payload path the lane publishes into the MACRO_LIVE_DIR ladder (design §2
#: step 9).  Deliberately NOT in the Caddy allowlist.
SERVED_URL_PATH = "/live/entry_radar.json"

#: The exact double gate.  Written out rather than substring-matched: the NESTING
#: is the security property (the program kill switch binds always; only the host
#: gate has a dispatch bypass), and a substring test passes on a re-parenthesised
#: expression that means something else entirely.
JOB_GATE = (
    "${{ vars.ENTRY_RADAR_LIVE_DISABLED != 'true' && "
    "(github.event_name == 'workflow_dispatch' || vars.VPS_LIVE_PRIMARY != 'true') }}"
)

#: The ONE cap set both units carry.  Two units of the same program that drift
#: apart on limits are two different failure envelopes to reason about.
SHARED_CAPS = {
    "Nice": "10",
    "CPUWeight": "20",
    "CPUQuota": "60%",
    "MemoryHigh": "256M",
    "MemoryMax": "512M",
    "IOWeight": "20",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _unit(path: Path) -> configparser.ConfigParser:
    # interpolation=None is load-bearing: `CPUQuota=60%` is a ConfigParser
    # interpolation syntax error, and a unit file is not an ini template.
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string(path.read_text(encoding="utf-8"))
    return cp


def _workflow() -> dict:
    """``yaml.safe_load`` of the backstop.  ``on:`` is YAML 1.1 True — see below."""
    return yaml.safe_load(WORKFLOW)


def _on_block(wf: dict) -> dict:
    # PyYAML resolves the bare key `on` to the BOOLEAN True (YAML 1.1). Reading
    # wf["on"] therefore KeyErrors on a perfectly valid workflow, which is the
    # kind of failure that gets "fixed" by deleting the assertion.
    return wf.get("on") or wf[True]


def _minute_offset(path: Path) -> tuple[int, int]:
    """``(offset, step)`` from a ``…:MM/STEP:00 UTC`` OnCalendar."""
    cal = _unit(path)["Timer"]["OnCalendar"]
    m = re.search(r":(\d+)/(\d+):00 UTC$", cal)
    assert m, f"{path.name}: unparseable OnCalendar {cal!r}"
    return int(m.group(1)), int(m.group(2))


def _caddy_public_exclusions() -> set[str]:
    # Copied from tests/test_prophet_live_vps_lane.py rather than imported: the
    # house pattern is one self-contained copy per lane suite (test_close_pass_lane
    # carries the same helper), so a lane's boundary test never fails because a
    # sibling suite moved a private helper.
    caddy = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    match = re.search(r"# PUBLIC-BOUNDARY-START.*?@reg_asset\s*\{\s*not path ([^\n]+)",
                      caddy, flags=re.S)
    assert match, "Caddy public-boundary matcher missing"
    return set(shlex.split(match.group(1)))


def _update_block() -> str:
    """The entry-radar self-arming block, cut out of update.sh by its own header.

    The end anchor is the FIRST sibling block header that follows, whichever it
    is — at the W4+W5 merge the customer-table backup block (MMX-001) landed
    between this block and PRESS-FEEDS, and slicing to PRESS-FEEDS alone would
    swallow it, importing its `grep -qE` into every count this suite asserts.
    """
    assert "# LIVE ENTRY RADAR lanes" in UPDATE_SH, "no entry-radar block in update.sh"
    block = UPDATE_SH.split("# LIVE ENTRY RADAR lanes")[1]
    ends = [block.index(marker) for marker in
            ("# CUSTOMER-TABLE BACKUP", "# PRESS-FEEDS is a long-running daemon")
            if marker in block]
    assert ends, "no sibling block follows the entry-radar block in update.sh"
    return block[:min(ends)]


def _changed_trigger() -> re.Pattern[str]:
    """The CHANGED regex, COMPILED OUT OF update.sh — never re-typed here."""
    block = _update_block()
    m = re.search(r"grep -qE '([^']+)'", block)
    assert m, "no CHANGED trigger in the entry-radar block"
    return re.compile(m.group(1))


# ─────────────────────────────────────────────────────────────────────────────
# Host units — the two services
# ─────────────────────────────────────────────────────────────────────────────

def test_both_services_are_capped_oneshots_on_the_lowest_priority_tier():
    """Caps are INHERITED from the prophet lane's measured envelope (the units say
    so in their own headers) and are no looser than the smallest sibling.  The tier
    matters: this program CONSUMES what the quote lanes publish, so it must always
    lose a scheduling contest with them."""
    for path in (EVAL_SERVICE, PACK_SERVICE):
        svc = _unit(path)["Service"]
        assert svc["Type"] == "oneshot", path.name
        assert svc["WorkingDirectory"] == "/opt/macro", path.name
        assert svc["EnvironmentFile"] == "-/etc/macro-live.env", path.name
        assert svc["NoNewPrivileges"] == "true", path.name
        assert svc["PrivateTmp"] == "true", path.name
        for key, value in SHARED_CAPS.items():
            assert svc[key] == value, f"{path.name}: {key}={svc[key]!r}"
        # Never looser than the lane whose measurement they inherit.
        bars = _unit(DEPLOY / "macro-live-bars.service")["Service"]
        assert int(svc["Nice"]) >= int(bars["Nice"]), path.name
        assert int(svc["CPUWeight"]) <= int(bars["CPUWeight"]), path.name
        assert int(svc["IOWeight"]) <= int(bars["IOWeight"]), path.name
        assert int(svc["CPUQuota"].rstrip("%")) <= 90, path.name   # <= snapshot/bars

        unit = _unit(path)["Unit"]
        assert unit["After"] == "network-online.target", path.name
        assert unit["Wants"] == "network-online.target", path.name
        assert _unit(path)["Install"]["WantedBy"] == "multi-user.target", path.name


def test_each_service_runs_its_own_module_and_nothing_else():
    """The two ExecStarts are the whole reason there are two units.  Asserted as
    full module paths: a pack builder invoked as the evaluator would publish a
    payload from a substrate nobody froze."""
    assert _unit(EVAL_SERVICE)["Service"]["ExecStart"] == (
        "/opt/macro/.venv/bin/python -m scripts.entry_radar_live")
    assert _unit(PACK_SERVICE)["Service"]["ExecStart"] == (
        "/opt/macro/.venv/bin/python -m scripts.entry_radar_live_pack")


def test_the_timeouts_are_bounded_inside_their_own_timer_periods():
    """Two passes of the same unit can never overlap — which is what makes the
    state-dir flock a SECOND guard rather than the only one.

    The evaluator's period is 300 s and the pack's is 3600 s, so the two timeouts
    are not the same number and must not be pinned as if they were: a 120 s cap on
    a batch pack build would kill every build it ever ran.
    """
    assert int(_unit(EVAL_SERVICE)["Service"]["TimeoutStartSec"]) == 120 <= 300
    assert int(_unit(PACK_SERVICE)["Service"]["TimeoutStartSec"]) == 1800 <= 3600 // 2


def test_no_unit_directive_runs_a_git_command_or_writes_a_data_path():
    """G0.2 at the unit layer.  Directives only — the header comments necessarily
    NAME the things they forbid, so a whole-file grep would fail on the prose that
    exists to explain the rule."""
    for path in UNIT_FILES:
        cp = _unit(path)
        for section in cp.sections():
            for key, value in cp[section].items():
                for banned in ("git ", "data/", "/opt/macro/site", "site.served"):
                    assert banned not in value, f"{path.name}: {key}={value}"


# ─────────────────────────────────────────────────────────────────────────────
# Host units — the two timers
# ─────────────────────────────────────────────────────────────────────────────

def test_the_evaluator_timer_covers_the_session_in_both_dst_regimes():
    """The UTC span covers 09:2x-16:2x ET under EDT AND EST; the ET trimming is done
    by the evaluator's own in_window, so "when is the market open" has exactly one
    definition and it is not in this file."""
    timer = _unit(EVAL_TIMER)["Timer"]
    cal = timer["OnCalendar"]
    assert cal == "Mon..Fri *-*-* 13..21:04/5:00 UTC"
    m = re.fullmatch(r"Mon\.\.Fri \*-\*-\* (\d+)\.\.(\d+):(\d+)/(\d+):00 UTC", cal)
    assert m, cal
    lo, hi, offset, step = (int(g) for g in m.groups())
    assert step == 5 and 0 <= offset < 5
    # EDT 09:25 ET = 13:25Z ... EST 16:25 ET (window end + grace) = 21:25Z.
    assert lo <= 13 and hi >= 21
    assert timer["AccuracySec"] == "1s"
    assert timer["RandomizedDelaySec"] == "10s"
    assert timer["Persistent"] == "false"        # never replay a missed pass
    assert timer["Unit"] == "macro-live-entry-radar.service"
    assert _unit(EVAL_TIMER)["Install"]["WantedBy"] == "timers.target"
    # No second window definition anywhere in the [Timer] section itself.
    assert "09:25" not in EVAL_TIMER.read_text(encoding="utf-8").split("[Timer]")[1]


def test_the_pack_timer_is_hourly_pre_open_in_both_dst_regimes():
    """10:20Z-13:20Z is 06:20-09:20 ET under EDT and 05:20-08:20 ET under EST — every
    attempt pre-open, and the LAST one still ahead of the evaluator's 09:25 ET
    window start, which is the ordering the stale-pack gate depends on."""
    timer = _unit(PACK_TIMER)["Timer"]
    cal = timer["OnCalendar"]
    assert cal == "Mon..Fri *-*-* 10..13:20:00 UTC"
    m = re.fullmatch(r"Mon\.\.Fri \*-\*-\* (\d+)\.\.(\d+):(\d+):00 UTC", cal)
    assert m, cal
    lo, hi, minute = (int(g) for g in m.groups())
    assert minute == 20
    # EDT: 13:20Z = 09:20 ET, five minutes ahead of the 09:25 ET window start; even
    # with the full RandomizedDelaySec the last attempt starts by 09:21 ET.
    assert hi + 1 <= 14, "the last pack attempt must not reach into the RTH window"
    assert lo <= 10, "the span must open early enough to absorb a late nightly"
    assert hi - lo >= 3, "hourly retries are the whole recovery mechanism"
    assert timer["AccuracySec"] == "1m"          # a pre-open batch job needs no second
    assert timer["RandomizedDelaySec"] == "60s"
    assert timer["Persistent"] == "false"        # never build mid-session after a reboot
    assert timer["Unit"] == "macro-entry-radar-pack.service"
    assert _unit(PACK_TIMER)["Install"]["WantedBy"] == "timers.target"


def test_the_evaluator_fires_behind_prophet_and_behind_the_snapshot_writer():
    """THE WRITER RACE, asserted by parsing ALL THREE timers rather than by reading
    one comment.

    macro-live-snapshot publishes the full-universe quote file on the :00/5
    boundary and takes up to ~230 s; Prophet reads it at :03/5; this lane reads the
    SAME artifacts at :04/5.  A future edit that moves any one of the three onto
    another's minute would put this lane back on last cycle's snapshot — silently,
    because a stale-but-whole quote file parses perfectly.  Pinning the RELATIONSHIP
    rather than the literal is what makes the edit to the OTHER file fail here.
    """
    radar_offset, radar_step = _minute_offset(EVAL_TIMER)
    prophet_offset, prophet_step = _minute_offset(PROPHET_TIMER)
    writer_offset, writer_step = _minute_offset(SNAPSHOT_TIMER)

    assert radar_step == prophet_step == writer_step == 5
    assert writer_offset == 0                       # the publication boundary
    assert prophet_offset == 3                      # Prophet's head start
    assert radar_offset == 4                        # ours
    assert radar_offset == prophet_offset + 1, "the one-minute separation is gone"
    assert radar_offset not in (prophet_offset, writer_offset), \
        "two capped oneshots now wake on the same second"
    assert radar_offset > writer_offset, "the reader must never precede the writer"


# ─────────────────────────────────────────────────────────────────────────────
# The GitHub backstop
# ─────────────────────────────────────────────────────────────────────────────

def test_the_backstop_is_read_only_and_never_commits():
    """LEDGER LAW G0.2 — and the reason this lane can stay armed at all.  W4 owns no
    durable ledger anywhere (design §0: zero data/entry_radar/** writes)."""
    wf = _workflow()
    assert wf["permissions"] == {"contents": "read"}
    for banned in ("git add", "git commit", "git push", "contents: write"):
        assert banned not in WORKFLOW, banned


def test_the_job_gate_is_the_exact_double_gate():
    """String equality, not a substring: the NESTING is the property."""
    assert _workflow()["jobs"]["evaluate"]["if"] == JOB_GATE


def test_the_program_kill_switch_is_not_bypassable_by_dispatch():
    """ENTRY_RADAR_LIVE_DISABLED binds ALWAYS; only the host gate has a dispatch
    bypass.  Evaluated for real, not read: the combinations are substituted into
    the expression the way GitHub evaluates it."""
    job = _workflow()["jobs"]["evaluate"]["if"].strip()
    expr = job[3:-2].strip() if job.startswith("${{") else job

    def evaluate(*, disabled: str, primary: str, event: str) -> bool:
        py = (expr.replace("vars.ENTRY_RADAR_LIVE_DISABLED", repr(disabled))
                  .replace("vars.VPS_LIVE_PRIMARY", repr(primary))
                  .replace("github.event_name", repr(event))
                  .replace("&&", "and").replace("||", "or"))
        return bool(eval(py))                                   # noqa: S307

    assert evaluate(disabled="", primary="", event="schedule") is True
    assert evaluate(disabled="", primary="true", event="schedule") is False
    assert evaluate(disabled="", primary="true", event="workflow_dispatch") is True
    assert evaluate(disabled="true", primary="true", event="workflow_dispatch") is False
    assert evaluate(disabled="true", primary="", event="workflow_dispatch") is False


def test_the_backstop_runs_off_the_render_path_and_never_cancels_a_pass():
    """ubuntu-latest, never the macstudio pool (runner-placement law).  And a pass in
    flight may already have spooled its events, so cancel-in-progress must stay
    false — spool-before-commit makes a cancelled pass the NEXT pass's problem."""
    wf = _workflow()
    job = wf["jobs"]["evaluate"]
    assert job["runs-on"] == "ubuntu-latest"
    # PARSED, not grepped: the header comment necessarily NAMES the pool it forbids,
    # so a raw-text search fails on the prose that exists to explain the rule.
    assert "self-hosted" not in yaml.dump(job)
    assert "macstudio" not in yaml.dump(job)
    assert wf["concurrency"]["group"] == "entry-radar-live"
    assert wf["concurrency"]["cancel-in-progress"] is False
    assert job["timeout-minutes"] == 20


def test_the_schedule_spans_both_dst_regimes_in_three_crons():
    """GitHub cron has no timezone.  Copied verbatim from prophet-live so the two
    lanes cannot end up with two definitions of "when is the market open"."""
    crons = [c["cron"] for c in _on_block(_workflow())["schedule"]]
    assert crons == [
        "25,30,35,40,45,50,55 13 * * 1-5",
        "*/5 14-20 * * 1-5",
        "0,5,10,15 21 * * 1-5",
    ]
    prophet = (ROOT / ".github" / "workflows" / "prophet-live.yml").read_text(
        encoding="utf-8")
    for cron in crons:
        assert f'cron: "{cron}"' in prophet, cron


def test_the_dispatch_carries_a_dry_run_input_and_both_scripts_honour_it():
    """The PR receipt mode.  Both halves of the cycle run, and both take --dry-run:
    a pack build that writes while the evaluator does not is a half-rehearsal."""
    wf = _workflow()
    inputs = _on_block(wf)["workflow_dispatch"]["inputs"]
    assert inputs["dry_run"]["type"] == "boolean"
    assert inputs["dry_run"]["default"] is False

    runs = "\n".join(s.get("run", "") for s in wf["jobs"]["evaluate"]["steps"])
    for module in ("scripts.entry_radar_live_pack", "scripts.entry_radar_live"):
        assert f"python -m {module}\n" in runs, module
        assert f"python -m {module} --dry-run" in runs, module
    # The pack build must precede the evaluator: the evaluator refuses a cycle whose
    # pack is not the last completed session, so the reverse order is always a
    # stale_pack no-op on a fresh runner checkout.
    assert runs.index("scripts.entry_radar_live_pack") < \
        runs.index("scripts.entry_radar_live --dry-run")


def test_the_checkout_cone_carries_the_daily_substrate_the_pack_freezes():
    """The one cone entry prophet-live does not need and this lane cannot do
    without.  The pack builder reads data/stocks/<SYM>.parquet per probe name; a
    cone that omits it makes every name unavailable on a runner, which reads as a
    quiet market rather than a broken checkout."""
    checkout = _workflow()["jobs"]["evaluate"]["steps"][0]
    assert checkout["uses"].startswith("actions/checkout@")
    cone = checkout["with"]["sparse-checkout"].split()
    assert "data/stocks" in cone
    for path in ("engine", "scripts", "lib", "collectors", "config", "site/live"):
        assert path in cone, path
    assert checkout["with"]["fetch-depth"] == 1
    assert checkout["with"]["filter"] == "blob:none"


# ─────────────────────────────────────────────────────────────────────────────
# W4R-LOW — the backstop's runtime state plane
#
# Review round 1, LOW batch.  Both scripts resolve their state dir as
# ``--state-dir`` -> ``$ENTRY_RADAR_STATE_DIR`` -> the VPS path, else None, and on
# a runner the VPS parent does not exist.  With the env unset the builder had
# nowhere to write the frozen pack and the evaluator loaded no pack at all, so
# every backstop run took the whole-cycle ``stale_pack`` refusal and exited 5 —
# a rollback path that could never once have evaluated a name.
#
# The env name is read OUT OF THE SCRIPTS rather than re-typed, so a rename that
# moves the contract reds here instead of silently un-wiring the lane again.
# ─────────────────────────────────────────────────────────────────────────────

def _state_dir_env_name() -> str:
    """The env var both scripts resolve, taken from the evaluator's own constant."""
    import scripts.entry_radar_live as ERL  # noqa: PLC0415
    import scripts.entry_radar_live_pack as ERP  # noqa: PLC0415
    assert ERL._STATE_DIR_ENV == ERP._STATE_DIR_ENV, (
        "the builder writes the plane the evaluator reads — one name or neither")
    return ERL._STATE_DIR_ENV


def test_W4R_LOW_the_backstop_exports_a_runner_local_state_dir():
    """Without it the lane is structurally incapable of a non-refusal pass."""
    name = _state_dir_env_name()
    steps = _workflow()["jobs"]["evaluate"]["steps"]
    exports = [s for s in steps if f'{name}=' in (s.get("run") or "")]
    assert len(exports) == 1, f"exactly one {name} export, found {len(exports)}"
    run = exports[0]["run"]
    assert f'echo "{name}=$RUNNER_TEMP/' in run, run
    assert '>> "$GITHUB_ENV"' in run, "the export must reach the LATER steps"
    assert "mkdir -p" in run, "the builder is handed a directory, not a promise"


def test_W4R_LOW_the_state_plane_is_exported_BEFORE_both_consumers():
    """A $GITHUB_ENV export is visible to SUBSEQUENT steps only.

    Exported after the pack build, the builder still writes nowhere and the
    evaluator reads an empty plane — the same exit 5, one step later.
    """
    name = _state_dir_env_name()
    steps = _workflow()["jobs"]["evaluate"]["steps"]
    runs = [s.get("run") or "" for s in steps]
    export_at = next(i for i, r in enumerate(runs) if f'{name}=' in r)
    for module in ("scripts.entry_radar_live_pack", "scripts.entry_radar_live"):
        consumer_at = next(i for i, r in enumerate(runs) if f"python -m {module}" in r)
        assert export_at < consumer_at, module


def test_W4R_LOW_the_state_plane_is_ONE_path_shared_by_both_steps():
    """The builder WRITES this plane and the evaluator READS it.

    Two step-local ``env:`` copies would satisfy the export test above and still
    let a future edit point the two halves at different directories — the pack
    would be built into a directory nothing ever loads, which is exit 5 again
    with every step green.
    """
    name = _state_dir_env_name()
    steps = _workflow()["jobs"]["evaluate"]["steps"]
    assert name not in yaml.dump(_workflow().get("env") or {})
    for step in steps:
        assert name not in (step.get("env") or {}), (
            f"{step.get('name')}: a step-local {name} is a SECOND definition")


def test_W4R_LOW_the_runner_state_plane_is_never_a_repo_path():
    """LEDGER LAW G0.2 is not relaxed by giving the lane somewhere to write.

    $RUNNER_TEMP is outside the checkout and wiped with the job, so the journal,
    ledger, heartbeat and bucket cache stay RUNTIME state.  The durable owner of
    this lane's history is the VPS.
    """
    name = _state_dir_env_name()
    run = next(s["run"] for s in _workflow()["jobs"]["evaluate"]["steps"]
               if f'{name}=' in (s.get("run") or ""))
    for banned in ("data/", "site/", "${{ github.workspace }}", "./"):
        assert banned not in run, banned
    import scripts.entry_radar_live as ERL  # noqa: PLC0415
    assert ERL.DURABLE_WRITES == (), "the evaluator's durable-write set stays empty"


def test_W4R_LOW_the_env_is_what_actually_moves_the_resolution(tmp_path,
                                                              monkeypatch):
    """The PREMISE, driven rather than asserted: unset -> None, set -> that path.

    Both halves matter.  ``None`` is the state the workflow was in, and it is
    what makes ``load_pack`` return nothing and the cycle refuse ``stale_pack``
    (pinned at ``tests/test_entry_radar_w4_liveness.py`` — exit 5).  Without this
    the structural assertions above pin a string with no consequence attached.
    """
    import scripts.entry_radar_live as ERL  # noqa: PLC0415
    import scripts.entry_radar_live_pack as ERP  # noqa: PLC0415
    name = _state_dir_env_name()
    absent = tmp_path / "no-such-vps-root" / "entry_radar"
    for module in (ERL, ERP):
        monkeypatch.setattr(module, "_VPS_STATE_DIR", absent)
        monkeypatch.delenv(name, raising=False)
        assert module.state_dir() is None, module.__name__

        monkeypatch.setenv(name, str(tmp_path / "runner-temp" / "entry-radar-state"))
        assert module.state_dir() == tmp_path / "runner-temp" / "entry-radar-state"
        # …and an explicit --state-dir still outranks it (the VPS ladder's order).
        assert module.state_dir(str(tmp_path / "cli")) == tmp_path / "cli"


def test_W4R_LOW_the_header_says_why_the_cold_plane_is_correct():
    """A reader who finds a state dir on a read-only lane must not have to guess.

    The cost is real and named: no journal replay, no ledger history, no warm
    bucket cache — so the backstop's payload is a liveness signal, not a ledger.
    """
    name = _state_dir_env_name()
    step = next(s for s in _workflow()["jobs"]["evaluate"]["steps"]
                if f'{name}=' in (s.get("run") or ""))
    assert "RUNNER-LOCAL" in step["name"] and "ephemeral" in step["name"]
    header = WORKFLOW.split("- name: build the evaluation pack")[0]
    for claim in ("stale_pack", "exit 5", "RUNNER_TEMP", "cold start", "LEDGER LAW"):
        assert claim in header, claim


def test_the_numeric_stack_is_installed_here_unlike_prophet_live():
    """pandas/numpy/pyarrow are REQUIRED: the pack freezes a parquet substrate and
    the evaluator runs the real indicator chain.  Prophet-live deliberately installs
    neither, which is why this cannot be copied from it without thinking."""
    install = next(s for s in _workflow()["jobs"]["evaluate"]["steps"]
                   if s.get("name") == "install deps")["run"]
    for pkg in ("pyyaml", "boto3", "pandas", "numpy", "pyarrow"):
        assert pkg in install, pkg


def test_the_r2_secrets_are_passed_exactly_as_the_sibling_lane_passes_them():
    """Same four names, same plane.  A renamed secret here publishes nothing and
    says nothing — the spool degrades silently by design."""
    steps = [s for s in _workflow()["jobs"]["evaluate"]["steps"] if s.get("env")]
    assert len(steps) == 2, "both run steps need the R2 plane"
    for step in steps:
        for name in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                     "R2_BUCKET"):
            assert step["env"][name] == "${{ secrets.%s }}" % name, (step["name"], name)


def test_the_workflow_header_says_it_is_a_dormant_backstop():
    """The header is the first thing the next reader believes.  Prophet-live learned
    this the expensive way: it advertised a 5-minute product cadence while GitHub
    was delivering ~90 minutes."""
    header = WORKFLOW.split("on:")[0]
    assert "BACKSTOP" in header
    assert "not the product cadence" in header
    assert "DORMANT" in header
    assert "macro-live-entry-radar" in header


# ─────────────────────────────────────────────────────────────────────────────
# macro-update — the self-arming block and its arm gate
# ─────────────────────────────────────────────────────────────────────────────

def test_the_changed_trigger_covers_the_units_and_the_code_they_run():
    """Derived, not eyeballed — the regex is compiled OUT of update.sh and applied
    to the paths it must match and to paths it must NOT.

    It covers the scripts and the engine's live_* modules as well as the units,
    because on this lane a code change with no unit change still needs the timers
    restarted: the oneshots import their code at start, so a merged fix that
    changes no .service file otherwise waits for the next unrelated unit edit.
    """
    trigger = _changed_trigger()
    for path in ("app/deploy/macro-live-entry-radar.service",
                 "app/deploy/macro-live-entry-radar.timer",
                 "app/deploy/macro-entry-radar-pack.service",
                 "app/deploy/macro-entry-radar-pack.timer",
                 "scripts/entry_radar_live.py",
                 "scripts/entry_radar_live_pack.py",
                 "engine/entry_radar/live_eval.py",
                 "engine/entry_radar/live_pack.py",
                 "engine/entry_radar/live_ledger.py"):
        assert trigger.search(path), path
    for path in ("app/deploy/macro-live-prophet.service",
                 "app/deploy/macro-live-prophet.timer",
                 "app/deploy/macro-live-closepass.timer",
                 "app/deploy/macro-live-entry-radar.service.bak",
                 "engine/entry_radar/spool.py",
                 "config.yml"):
        assert not trigger.search(path), path


def test_the_block_installs_under_the_same_narrow_reconciler_discipline():
    """A broken unit never installs; installing twice is a no-op; the absent-file
    clause self-heals a failed verify or an operator removal."""
    block = _update_block()
    assert "systemd-analyze verify" in block
    assert "cmp -s" in block
    assert "install -m 0644" in block
    assert "daemon-reload" in block
    assert "RECONCILED=1" in block
    assert "systemctl enable --now macro-live-entry-radar.timer" in block
    assert "macro-entry-radar-pack.timer" in block
    assert "[ ! -f /etc/systemd/system/macro-live-entry-radar.timer ]" in block
    assert "[ ! -f /etc/systemd/system/macro-entry-radar-pack.timer ]" in block
    # Inert on any host without the live plane — the same guard every sibling block
    # uses to mark the serving VPS.
    assert "systemctl is-enabled macro-live-fast.timer" in block


def test_the_arm_gate_reads_the_operator_flag_and_refuses_to_install_without_it():
    """Go-live is an explicit OPERATOR act, not a repo commit (design §3b).  The
    exact log line is pinned because it is the operator-visible evidence that a
    merged, deployed, verified lane is deliberately doing nothing."""
    block = _update_block()
    assert "ENTRY_RADAR_LIVE_ENABLE" in block
    assert "/etc/macro-live.env" in block
    assert ('echo "macro-update: entry-radar: staged, not armed '
            '(ENTRY_RADAR_LIVE_ENABLE unset)"') in block
    # Read by grep, never sourced: update.sh runs as root under `set -euo pipefail`
    # and sourcing an operator-edited file would execute it in this shell.
    assert "source /etc/macro-live.env" not in UPDATE_SH
    assert ". /etc/macro-live.env" not in UPDATE_SH
    # `|| true` on the extraction: under pipefail an unmatched grep is exit 1, and
    # `set -e` would make the ORDINARY unarmed path fatal.
    arm_line = next(ln for ln in block.splitlines() if "ENTRY_RADAR_ARM=" in ln)
    assert "grep -E '^ENTRY_RADAR_LIVE_ENABLE='" in arm_line
    assert "|| true" in block.split("ENTRY_RADAR_ARM=")[1].split("\n\tif ")[0]


def test_the_disarm_is_symmetric_and_sits_outside_the_changed_trigger():
    """THE STRUCTURAL POINT OF THIS BLOCK.

    Rollback is "delete the env line" (W4_DEPLOY_PLAN.md §4), which touches NO repo
    file — so a disarm nested inside the CHANGED trigger would never fire and the
    timers would keep running forever after the operator believed they had stopped.
    The arm check therefore sits ABOVE the CHANGED trigger, and only the INSTALL
    half is CHANGED-gated.

    Asserted by ORDER inside the block: arm read → CHANGED trigger (exactly once,
    in the armed branch) → the arm check's `else` → the disarm.  A future edit that
    wraps the disarm in a second CHANGED gate moves `grep -qE` past the `else` and
    fails here.
    """
    block = _update_block()
    assert block.count("grep -qE") == 1, \
        "a second CHANGED gate appeared — the disarm must not be behind one"
    arm_else = block.index("\n\telse\n")
    assert block.index("ENTRY_RADAR_ARM=") < block.index("grep -qE") < arm_else
    assert arm_else < block.index("staged, not armed")
    assert arm_else < block.index("disable --now")
    assert ("systemctl disable --now macro-live-entry-radar.timer "
            "macro-entry-radar-pack.timer") in block
    assert "entry-radar: disarmed" in block
    # And the disarm only runs when there is something to disarm.
    disarm = block[arm_else:]
    assert "[ -f /etc/systemd/system/macro-live-entry-radar.timer ]" in disarm


def test_macro_update_never_restarts_the_entry_radar_oneshots():
    """`systemctl restart` on a oneshot RUNS it: an evaluator pass outside the ET
    window against a stale pack, or a pack build mid-session the stale-pack gate
    would then have to refuse.  Only the timers are (re)armed."""
    for unit in ("macro-live-entry-radar.service", "macro-entry-radar-pack.service"):
        assert f"restart {unit}" not in UPDATE_SH, unit
        assert f"start {unit}" not in UPDATE_SH, unit
    # And no sibling block was widened to sweep these units in.
    for marker in ("# PROPHET LIVE evaluator lane", "# CLOSE-PASS MIRROR lane",
                   "# FRESHNESS SENTINEL"):
        sibling = UPDATE_SH.split(marker)[1].split("# LIVE ENTRY RADAR lanes")[0]
        assert "entry-radar" not in sibling and "entry_radar" not in sibling, marker


# ─────────────────────────────────────────────────────────────────────────────
# The serving gate — /live/entry_radar.json inherits auth BY OMISSION
# ─────────────────────────────────────────────────────────────────────────────

def test_the_payload_is_not_in_the_caddy_public_allowlist():
    """Design §3b promises ZERO Caddyfile edits: the payload is auth-gated by
    construction because the boundary matcher is default-deny.  A promise kept at
    merge is not a promise kept — this is the tripwire for the next boundary edit.

    The payload carries per-name lane states, arm/candidate levels and probe-set
    membership; #3391 is the standing ruling that the real board is not free
    content, and this is the same content earlier.
    """
    assert SERVED_URL_PATH not in _caddy_public_exclusions()
    assert "entry_radar" not in (DEPLOY / "Caddyfile").read_text(encoding="utf-8")


def test_the_public_live_exceptions_are_still_exactly_the_reviewed_files():
    """A PREFIX would have swept the payload in with them.  There is no prefix —
    each entry is an individually reviewed file."""
    live_public = sorted(p for p in _caddy_public_exclusions() if p.startswith("/live/"))
    # Twin of the same inventory in tests/test_close_pass_lane.py; see the longer
    # note there. flow_pulse.json and intraday_quotes.json were made anonymously
    # fetchable on purpose by #6105 (2026-08-20) and neither copy of this list was
    # updated, so both have been red on main since. Healed together — a pack is one
    # check, so healing only one copy would deadlock the other.
    assert live_public == ["/live/breadth.json", "/live/flow_pulse.json",
                           "/live/intraday_quotes.json", "/live/quotes.json",
                           "/live/release_publications.json", "/live/staleness.json"]


# ─────────────────────────────────────────────────────────────────────────────
# Liveness — the freshness-sentinel registration
# ─────────────────────────────────────────────────────────────────────────────

def _sentinel_entry() -> dict:
    matches = [s for s in FS.SURFACES if s.get("id") == "entry_radar_live"]
    assert len(matches) == 1, f"expected one entry_radar_live surface, got {matches}"
    return matches[0]


def test_the_sentinel_registration_is_exactly_the_mandated_shape():
    """Design §3b: ONE dict, session-grain, absent_ok.  Asserted as full equality
    rather than key-by-key — an extra key here is a budget nobody reviewed, and the
    sentinel's contract is that every surface's judgement is legible from its row.
    """
    assert _sentinel_entry() == {
        "id": "entry_radar_live",
        "kind": "live_file",
        "path": "/live/entry_radar.json",
        "bake_budget_hours": None,
        "delay_budget_days": None,
        "asof_field": "asof",
        "asof_max_sessions_behind": 1,
        "absent_ok": True,
    }


def test_absence_is_the_pre_activation_state_and_never_pages():
    """The lane ships staged-not-armed, so from the merge until the operator's act
    there is no writer and nothing to serve.  Without absent_ok a missing file would
    page "the sentinel is blind" every 30 minutes from the day W4 lands — the
    false-positive factory the module's own falsifier law forbids."""
    entry = _sentinel_entry()
    assert entry["absent_ok"] is True
    # The same exemption the evening board and the CN runtime board carry, each
    # for a different cause — and the only three surfaces that carry it, so the
    # exemption stays reviewed.
    absent_ok = {s["id"] for s in FS.SURFACES if s.get("absent_ok")}
    assert absent_ok == {"us_board_provisional", "entry_radar_live", "cn_board_live"}


def test_the_registration_is_the_only_surface_on_that_path():
    """Two surfaces on one path is two budgets and two verdicts for one artifact."""
    on_path = [s for s in FS.SURFACES if s.get("path") == "/live/entry_radar.json"]
    assert len(on_path) == 1
    assert on_path[0]["kind"] == "live_file"
    # Nothing else in SURFACES was disturbed: the sibling live_file entry is intact.
    assert {s["id"] for s in FS.SURFACES} >= {
        "us_stocks", "china", "hub", "r2_massive_stock_day", "prophet_us",
        "us_board_provisional", "entry_radar_live"}


def test_the_budget_is_a_session_budget_not_a_wall_clock_one():
    """1 completed session absorbs a single miss; the SECOND is a definitive breach —
    the same anchor prophet_us uses, and calendar-aware by construction so weekends
    and holidays add zero."""
    entry = _sentinel_entry()
    assert entry["asof_max_sessions_behind"] == FS.PROPHET_MAX_SESSIONS_BEHIND == 1
    # No bake stamp to anchor on: this artifact is judged on CONTENT.
    assert entry["bake_budget_hours"] is None
    assert entry["delay_budget_days"] is None
    assert entry["asof_field"] == "asof"


# ─────────────────────────────────────────────────────────────────────────────
# The hot-tape tap — the W1-designated PR-4 integration point
# ─────────────────────────────────────────────────────────────────────────────

def test_the_tap_is_wired_immediately_after_detect_events():
    """W1 designated this exact call site (engine/entry_radar/spool.py docstring).
    hot_tape is Radar's one producer with NO artifact to adapt: the detection exists
    only in that variable, so it is captured here or it is unreconstructible."""
    assert "spool_hot_tape" in HOT_TAPE_SRC
    assert "from engine.entry_radar.spool import spool_hot_tape" in HOT_TAPE_SRC
    assert HOT_TAPE_SRC.index("HT.detect_events(") < HOT_TAPE_SRC.index(
        "spool_hot_tape(events")


def test_the_tap_carries_the_quote_merge_vintage_not_the_wall_clock():
    """source_asof is the LIVE QUOTE MERGE timestamp, parsed from live["asof"] (an
    ISO string out of live_verify) to an aware datetime by the file's own _parse_iso.

    The two wrong answers in scope at that call site are both plausible and both
    silent: `ts` is NOW (it would date every nomination to the pass, erasing the
    tape vintage the PIT question needs) and `as_of` is an ET DATE (not a datetime
    at all, and a day-grain stamp on an intraday detection).
    """
    assert "spool_hot_tape(events, source_asof=_parse_iso(live.get(\"asof\")))" \
        in HOT_TAPE_SRC
    assert "spool_hot_tape(events, source_asof=ts)" not in HOT_TAPE_SRC
    assert "spool_hot_tape(events, source_asof=as_of)" not in HOT_TAPE_SRC


def test_the_tap_does_NOT_fire_in_demo_or_dry_run():
    """A rehearsal must not enter the accrual stream.

    ``--demo`` runs the detectors against a QUIET OR CLOSED tape under a relaxed
    freshness ceiling — real code paths over an unreal tape.  Spooled, those
    detections would carry ``data_quality="ok"`` and a vintage that reads as
    current, and ``engine/entry_radar/spool.py`` is explicit that a fabricated row
    joined to real closes is indistinguishable from a genuine one FOREVER: there
    is no later pass that can un-poison it.  ``--dry-run`` is gated for
    consistency with every other side effect in the same function — ``roll_ring``,
    ``emit`` and ``dispatch_ids`` are all ``if not dry_run``, and a rehearsal that
    silently published to a private operational prefix would be the one write a
    dry run did not disclose.

    Pinned on the SOURCE rather than by driving the lane because the surrounding
    entry point needs a full marketing fixture (pack, heatmap, earnings, ring) to
    reach this line; the gate is one branch and its absence is what matters.
    """
    gate = HOT_TAPE_SRC.index("if not demo and not dry_run:")
    call = HOT_TAPE_SRC.index("spool_hot_tape(events")
    assert gate < call, "the tap is not behind the demo/dry-run gate"
    assert HOT_TAPE_SRC.count("spool_hot_tape(events") == 1, \
        "a second, ungated call site would defeat the gate"
    # The gate must guard the CALL, not merely precede it somewhere in the file.
    between = HOT_TAPE_SRC[gate:call]
    assert between.count("\n") <= 2, \
        f"the gate is {between.count(chr(10))} lines above the call — not guarding it"


def test_the_tap_turns_detected_events_into_nominations():
    """Non-vacuous: a real event list produces a real nomination carrying the
    vintage, and the tap accepts both dicts and objects because it does not own
    hot_tape's row type."""
    events = [{"ticker": "AAPL", "kind": "gap", "change_pct": 5.0},
              {"ticker": "", "kind": "noise"}]          # nameless rows are dropped
    noms = tap_hot_tape_events(events, source_asof=NOW, now=NOW)
    assert [n.ticker for n in noms] == ["AAPL"]
    assert noms[0].source_id == "hot_tape:detect_events"
    assert noms[0].reason_code == "hot_tape.gap"
    assert noms[0].source_asof == NOW
    assert noms[0].data_quality == "ok"
    # And an unknown vintage is declared, never invented — which is what the
    # call site's _parse_iso returning None degrades to.
    assert tap_hot_tape_events(events, now=NOW)[0].data_quality == "degraded"


@pytest.fixture
def hermetic_spool(monkeypatch, tmp_path):
    """No R2, no ambient spool dir, no publish switch — the sink is ours alone."""
    for name in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                 "R2_BUCKET", "ENTRY_RADAR_SPOOL_DIR", "ENTRY_RADAR_NO_PUBLISH"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_a_failing_r2_sink_degrades_to_a_warning_and_never_reaches_the_lane(
        hermetic_spool, capsys):
    """THE PROPERTY THE MARKETING LANE DEPENDS ON.  scripts/hot_tape_radar fails
    toward "no post": every step is never-raise and degrades to booking nothing.  A
    tap that propagated a transport error would crash a lane that runs 81 times a
    day over a spool object nobody is waiting on.

    Driven through the REAL failure the production sink has — put_object raising —
    not through a stubbed return value, because the swallow lives in _put's
    `except Exception`, not in the caller.
    """
    class ExplodingR2:
        def put_object(self, **kwargs):
            raise RuntimeError("R2 is down")

    events = [{"ticker": "AAPL", "kind": "gap", "change_pct": 5.0}]
    result = spool_hot_tape(events, source_asof=NOW, now=NOW,
                            spool=NominationSpool(s3=ExplodingR2()))
    assert result is None                      # nothing was spooled, and it said so
    warns = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert warns, "a silent spool failure is the one outcome that must not happen"
    assert all(ln.startswith("::warning title=entry-radar-spool::") for ln in warns), \
        "annotations must START the line — a logger prefix makes GitHub drop them"
    assert any("NOT spooled" in ln for ln in warns)


def test_a_healthy_local_sink_proves_the_failure_test_is_not_vacuous(hermetic_spool):
    """The control.  Same call, a sink that works: a key comes back and the
    returned object lands under the injected hermetic_spool — outside repo data/.

    W5 nightly reconciliation (W5 #5741) lawfully owns durable
    ``data/entry_radar/**``; ``ledger_state.json`` on main is that writer, not a
    W4 leak.  W4's invariant is narrower: an injected local sink writes the
    returned spool object only under that sink, never into repo ``data/``.
    """
    spool = NominationSpool(local_dir=hermetic_spool)
    key = spool_hot_tape([{"ticker": "AAPL", "kind": "gap", "change_pct": 5.0}],
                         source_asof=NOW, now=NOW, spool=spool)
    assert key == "live_flow/entry_radar_nominations/2026-08-14/140000-hot_tape.json"
    assert spool.written_keys == [key]
    # Nightly W5 owns durable data/entry_radar/** (ledger_state.json). Do not
    # assert that directory is absent — existence is not evidence about this call.
    # W4 invariant: the injected hermetic sink wrote the object under that sink,
    # never under repo data/.
    spooled = (hermetic_spool / key).resolve()
    data_root = (ROOT / "data").resolve()
    assert spooled.is_file()
    assert hermetic_spool.resolve() in spooled.parents
    assert not spooled.is_relative_to(data_root)


def test_an_exception_raised_by_put_itself_propagates_documented_finding(
        hermetic_spool):
    """PINS THE ACTUAL BEHAVIOUR, WHICH IS NOT THE ADVERTISED ONE.

    ``NominationSpool.append`` calls ``self._put(key, payload)`` with NO try/except
    around it, so ``spool_hot_tape`` swallows only the failures ``_put`` MODELS
    INTERNALLY — an unencodable payload, an exception from ``s3.put_object``, an
    OSError on the local write.  Those are the production failure modes and they are
    covered (test above), which is why the call site's comment claims what it claims.
    But an exception from any path ``_put`` does not model reaches the caller.

    Asserted rather than fixed: widening ``append`` to swallow everything would also
    swallow the programming errors this spool needs to surface, and the spool module
    belongs to another builder in this wave.  If a later PR adds a guard, this test
    is the one to update — deliberately, not by accident.
    """
    class RaisingPut(NominationSpool):
        def _put(self, key, payload):           # noqa: D102 - the injected fault
            raise RuntimeError("sink exploded in a way _put does not model")

    with pytest.raises(RuntimeError, match="sink exploded"):
        spool_hot_tape([{"ticker": "AAPL", "kind": "gap", "change_pct": 5.0}],
                       source_asof=NOW, now=NOW, spool=RaisingPut())


def test_an_eventless_pass_spools_nothing_at_all(hermetic_spool):
    """One object per pass-WITH-events.  81 empty objects a day would be a cost with
    no record in it, and the tap must not turn a quiet tape into traffic."""
    spool = NominationSpool(local_dir=hermetic_spool)
    assert spool_hot_tape([], source_asof=NOW, now=NOW, spool=spool) is None
    assert spool.written_keys == []
    assert list(hermetic_spool.iterdir()) == []
