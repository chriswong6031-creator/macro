"""closing-bell duplicate-render dedup: the stamp WRITER and the guard READER
must name the same field, and that field must be a bare session date.

THE DEFECT THIS PINS (measured 2026-08-09, fixed in the same PR)
---------------------------------------------------------------
`.github/workflows/closing-bell.yml` fires a DST cron pair; in summer the
21:05-UTC line lands at 17:05 ET, an hour after the 16:05-ET render, and the
session-day guard is supposed to skip it (`exit 5`, "already rendered this
session"). It never did. The guard compared

    st.get('as_of') == et.isoformat()          # "2026-08-07T23:11:28Z" == "2026-08-07"

against a stamp whose `as_of` is a full ISO TIMESTAMP. The bare date lives in
the sibling key `session`, which the guard never read, so the comparison was
False on every run the lane has ever made. Fallout: the lane rendered TWICE on
7/7 sampled trading days, the duplicate burning a median 85.0 min (n=5: 64.3 /
80.8 / 85.0 / 87.4 / 93.3) of `[self-hosted, macstudio]` time — a two-Mac pool —
inside the 22:10-00:22Z window the nightly's 22:30Z cron fires into.

It was NOT a race. `concurrency: pipeline-closingbell` already serializes the
pair: on 2026-08-05 the sibling ended 22:49:07Z, the duplicate's job started
22:49:08Z and pulled main at 22:49:21Z — it HELD the fresh stamp and proceeded
anyway. Only the field name was wrong, which is why a wall-clock or
concurrency-shaped test would have stayed green through the whole outage.

WHY THESE TESTS ARE SHAPED THIS WAY
-----------------------------------
Both halves are extracted from the workflow YAML and EXECUTED/EVALUATED as
written — never retyped here. A mirrored copy of the guard would have passed
against a mirrored copy of the writer while production stayed broken (the
tests/test_check_ms_board_coherence.py "mirrored guard is vacuous" class), so
the writer heredoc is run for real in a tmp tree and the guard's own comparison
expression is pulled out of the file and evaluated against that real output.

`test_dedup_expression_can_see_the_defect` is the negative control: it re-runs
the SAME extracted expression with the old field substituted back in and asserts
it goes False. Without it, a test that only asserts "the expression is True"
could pass for reasons unrelated to the field (memory: a refutation needs a
check that can actually see the failure).

Run: .venv/bin/python -m pytest tests/test_closingbell_dedup_contract.py -q
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "closing-bell.yml"

GUARD_STEP = "session-day guard (holiday/weekend/pre-close/duplicate safety)"
STAMP_STEP_PREFIX = "write provisional closingbell stamp"

#: The guard's duplicate-skip comparison, as it appears in the YAML. The capture
#: group is the stamp field the guard dedups on.
_DEDUP_RE = re.compile(r"st\.get\('([A-Za-z_]+)'\)\s*==\s*et\.isoformat\(\)")
_BARE_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


# ---------------------------------------------------------------------------
# extraction — the real file, never a copy
# ---------------------------------------------------------------------------

def _steps() -> list[dict]:
    doc = yaml.safe_load(WORKFLOW.read_text())
    return doc["jobs"]["closingbell"]["steps"]


def _step_run(match) -> str:
    for step in _steps():
        if match(step.get("name") or ""):
            run = step.get("run") or ""
            assert run, "step found but carries no `run:` body"
            return run
    raise AssertionError(
        f"no step in {WORKFLOW.name} matched — the step was renamed or removed, "
        "which silently un-pins this contract"
    )


def _guard_run() -> str:
    return _step_run(lambda n: n == GUARD_STEP)


def _stamp_python() -> str:
    """The stamp writer's python heredoc body (between the PYEOF markers)."""
    run = _step_run(lambda n: n.startswith(STAMP_STEP_PREFIX))
    body = re.search(r"<<'PYEOF'\n(.*?)\n\s*PYEOF", run, re.DOTALL)
    assert body, "stamp writer heredoc markers moved — extraction is no longer honest"
    return body.group(1)


def _dedup_field() -> str:
    hits = _DEDUP_RE.findall(_guard_run())
    assert len(hits) == 1, (
        f"expected exactly one duplicate-skip comparison in the guard, found {hits}. "
        "Two comparisons (or none) means this contract is no longer pinned."
    )
    return hits[0]


@pytest.fixture(scope="module")
def written_stamp(tmp_path_factory) -> dict:
    """Run the REAL stamp-writer heredoc in an isolated tree and return its output.

    `lib` is symlinked rather than copied so the writer imports the same
    lib.nyse_calendar the runner does; it is stdlib-only, so nothing else is
    needed. The writer hardcodes site/live/closingbell_stamp.json relative to
    cwd, hence the tmp cwd — this must never touch the repo's committed stamp.
    """
    tmp = tmp_path_factory.mktemp("closingbell")
    (tmp / "lib").symlink_to(ROOT / "lib", target_is_directory=True)
    script = tmp / "_write_stamp.py"
    script.write_text(_stamp_python())

    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, (
        f"the stamp writer heredoc does not run standalone:\n{proc.stderr}"
    )
    out = tmp / "site" / "live" / "closingbell_stamp.json"
    assert out.exists(), f"writer produced no stamp at {out}"
    return json.loads(out.read_text())


# ---------------------------------------------------------------------------
# the contract
# ---------------------------------------------------------------------------

def test_dedup_field_is_written_as_a_bare_session_date(written_stamp):
    """The field the guard reads must round-trip to `YYYY-MM-DD`.

    This is the assertion that fails on the shipped bug: with the guard reading
    `as_of`, the value is "2026-08-07T23:11:28Z" and can never equal a bare
    et.isoformat().
    """
    field = _dedup_field()
    assert field in written_stamp, (
        f"the guard dedups on {field!r} but the stamp writer never emits that key "
        f"(it writes {sorted(written_stamp)}). The skip is a permanent no-op."
    )
    value = written_stamp[field]
    assert _BARE_DATE_RE.fullmatch(str(value)), (
        f"the guard compares stamp[{field!r}] to et.isoformat() (a bare date) but the "
        f"writer emits {value!r}. These can never be equal, so the duplicate render "
        "would run every trading day."
    )


def test_dedup_expression_is_true_for_a_same_session_rerun(written_stamp):
    """Evaluate the guard's OWN comparison against the writer's real output."""
    expr = _DEDUP_RE.search(_guard_run()).group(0)
    et = date.fromisoformat(written_stamp["session"])
    assert eval(expr, {}, {"st": written_stamp, "et": et}) is True, (  # noqa: S307
        f"the guard's own expression ({expr}) does not fire for a second run in the "
        "same session — the duplicate render is not deduped"
    )


def test_dedup_expression_can_see_the_defect(written_stamp):
    """Negative control: the pre-fix field must make the SAME expression False.

    Guards against a test that passes for a reason unrelated to the field.
    """
    expr = _DEDUP_RE.search(_guard_run()).group(0)
    broken = expr.replace(f"'{_dedup_field()}'", "'as_of'")
    et = date.fromisoformat(written_stamp["session"])
    assert eval(broken, {}, {"st": written_stamp, "et": et}) is False, (  # noqa: S307
        "reading 'as_of' no longer breaks the dedup — this test can no longer see "
        "the defect it exists to pin, so the positive case above proves nothing"
    )


def test_as_of_and_session_stay_distinct_fields(written_stamp):
    """`as_of` keeps its timestamp; `session` keeps the bare date.

    Collapsing them (e.g. "fixing" the bug by making as_of a date) would silently
    change the human/provenance record every other reader of this stamp sees.
    """
    assert "as_of" in written_stamp and "session" in written_stamp
    assert not _BARE_DATE_RE.fullmatch(str(written_stamp["as_of"])), (
        "as_of collapsed to a bare date — it is the render TIMESTAMP; dedup belongs "
        "on `session`"
    )
    assert _BARE_DATE_RE.fullmatch(str(written_stamp["session"]))


def test_guard_keeps_its_other_skip_conditions():
    """The duplicate-skip fix must not be 'delete the guard'.

    All three documented exits stay wired, including the pre-close bound that is
    the WINTER half of the DST pair (20:05 UTC = 15:05 ET in EST — mid-session).
    """
    guard = _guard_run()
    for needle, why in (
        ("is_session", "holiday/weekend skip (exit 3)"),
        ("'1602'", "pre-close bound — the EST 15:05-ET cron must not render mid-session"),
        ("sys.exit(3)", "holiday/weekend exit"),
        ("sys.exit(4)", "pre-close exit"),
        ("sys.exit(5)", "already-rendered-this-session exit"),
    ):
        assert needle in guard, f"guard lost {needle} — {why}"


def test_dst_cron_pair_is_still_a_pair():
    """Both DST lines must survive: the dedup is what makes the pair safe.

    If a later change drops one cron instead of fixing the dedup, one DST regime
    loses its close render entirely — the failure mode this guard replaced.
    """
    doc = yaml.safe_load(WORKFLOW.read_text())
    # PyYAML parses the bare `on:` key as the boolean True.
    trigger = doc.get("on") or doc.get(True)
    crons = [c["cron"] for c in trigger["schedule"]]
    assert crons == ["5 20 * * 1-5", "5 21 * * 1-5"], (
        f"closing-bell DST cron pair changed to {crons}; re-derive the guard's "
        "pre-close bound and this test before shipping"
    )
