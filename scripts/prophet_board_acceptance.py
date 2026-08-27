#!/usr/bin/env python3
"""scripts/prophet_board_acceptance.py — post-publish acceptance alarm for one
engine-job nightly run.

PR-1 of the Prophet US permanence net (ROUTE: build commission,
research/PROPHET_US_PERMANENCE_NET_2026-08-27.md). An opus red-team of the
first design found that every existing watchdog (freshness_sentinel,
check_nightly_liveness, prophet_rescue) grades the estate from OUTSIDE the
run that produced it — after the fact, on a later cadence. None of them can
say "this run's own board is internally consistent" AT THE MOMENT it was
written, with the run's own on-disk bytes still in front of it. This script
closes that gap: it runs as the LAST prophet-owned step of the ENGINE job in
.github/workflows/daily.yml, immediately after the "Prophet nightly" step and
BEFORE "checkpoint Prophet outputs to main" — same job, same runner, same
files, so there is no cross-job pull race and no window where a later reader
could see something this check did not.

WHAT IT ASSERTS, for the session this run is producing (expected_last_session
against the clock the run started with):
  * IF this run originated any new plan (per the origination receipt
    mechanism the "Prophet nightly" step already writes), an immutable
    receipt exists for THIS run id at
    data/prophet/origination_receipts/<run_id>-*.json. A night with ZERO new
    originations legitimately writes NO receipt (build_prophet's own
    ``if not new_ids: raise SystemExit(0)``), so this is conditioned on the
    cohort being non-empty — an absent receipt on an honestly-empty night
    must never be a false alarm.
  * The intake identity holds: intake.lossless is True, intake.unaccounted
    == 0, and NOT (intake.eligible_after_skips > 0 AND intake.originated ==
    0). This is the SAME predicate scripts/freshness_sentinel.py,
    scripts/check_nightly_liveness.py, and scripts/prophet_rescue.py each
    carry independently — deliberately duplicated, never imported from one
    shared module, so a bug in one instrument's copy cannot blind the other
    three at once (see their own docstrings on failure-domain independence).
  * site/factordata/us_standouts.json's ``as_of`` equals both the expected
    session AND its own ``staleness.price_through`` — the same re-stamp trap
    freshness_sentinel's module docstring documents at length: a rerun over
    frozen inputs can re-stamp a publication clock green while the priced
    watermark stays behind.
  * every site/prophet/index.json plan recorded for this session
    (``recorded_at`` truncated to date == session) has its
    site/prophet/plans/<id>.json file present on disk.
  * every plan this run's receipt(s) say it newly originated carries a
    ``recorded_at`` stamp on disk.

HONEST SCOPE — read this before treating a green run as proof of more than it
is:
  * This is an ALARM AFTER PUBLISH, never a GATE. A failure here prints one
    ``::error`` annotation, pushes one ops alert, and exits nonzero — it does
    not and must never block the engine job's downstream steps or the
    nightly's site publish (see the caller step's own comment in daily.yml).
    Its job is to make a broken board LOUD on the GitHub failure domain the
    same night it breaks, closing the "everything green, board frozen" blind
    spot the August 2026 27-day freeze exposed.
  * It is a correct, honest NO-OP on a night the engine job never runs at all
    (a DST/weekend no-op skip) — nothing was owed, so there is nothing to
    check.
  * It is DEAD if the run is cancelled or wedged before this step ever
    starts. That failure class — a run that never concludes, is
    force-cancelled, or hangs — is covered by scripts/check_nightly_liveness.py
    (checks A/B) and scripts/prophet_rescue.py's wedge/strand logic, not by
    this script; a script that only runs inside a job cannot observe the job
    never finishing.
  * Under ``workflow_dispatch`` (a manual re-run, not the scheduled nightly)
    it additionally prints a line-start ``::warning`` noting that the
    schedule-only B1 candidate-episode reconcile step is skipped this run.
    That is informational only — this script does not touch and has no
    opinion on that step's trigger, which the V4 program owns.

Usage:
  python3 -m scripts.prophet_board_acceptance --run-id "$GITHUB_RUN_ID"
  python3 -m scripts.prophet_board_acceptance --now 2026-08-25T05:00:00+00:00 \\
      --root /path/to/checkout --run-id 123456   # offline / test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# UNCONDITIONAL, like every other guard script in this family (see
# scripts/check_nightly_liveness.py's own comment on this exact line): this
# runs as a bare ``python3 -m scripts.prophet_board_acceptance`` from
# daily.yml's engine job, whose sys.path[0] is not guaranteed to be the repo
# root.
sys.path.insert(0, str(REPO_ROOT))

from lib.nyse_calendar import expected_last_session  # noqa: E402

#: The annotation title every ``::error``/``::warning`` this script emits
#: carries. scripts/check_nightly_liveness.py's lane-latch exemption matches
#: on this exact string (via its job-steps read) to decide that a red run
#: reaching this step must reach fail_reasons and page rather than being
#: downgraded as a single-lane latch — so this constant is a cross-file
#: contract, not a local convenience. Keep it in lockstep with
#: ACCEPTANCE_ANNOTATION_TITLE in scripts/check_nightly_liveness.py.
ANNOTATION_TITLE = "prophet-board-acceptance"


def _load_json(path: Path) -> object | None:
    """A parsed JSON document, or None on anything short of success. Never raises —
    an absent or malformed file is exactly the class of thing this script exists
    to report, not to crash on."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def intake_identity_breach(intake: object) -> str | None:
    """Breach reason(s) from ``site/prophet/index.json``'s ``intake`` block, or
    None when it is healthy.

    DELIBERATELY DUPLICATED in scripts/freshness_sentinel.py,
    scripts/check_nightly_liveness.py, and scripts/prophet_rescue.py rather than
    imported from here or from one shared module: this permanence net's whole
    point is a SECOND, INDEPENDENT failure domain — a bug in one copy of this
    ~10-line predicate must never blind the other three instruments that also
    carry it. Keep the four copies in semantic lockstep by hand; a shared helper
    would defeat the reason they are four copies.

    An entirely absent/non-dict ``intake`` ABSTAINS (returns None). This
    function is called from ``check()`` only after ``site/prophet/index.json``
    itself was already confirmed readable, so an absent intake block here is a
    real production anomaly worth its own line — ``check()`` reports it via its
    own explicit index-readability message, not by this predicate inventing a
    breach text for a shape it cannot describe precisely.
    """
    if not isinstance(intake, dict):
        return None
    reasons: list[str] = []
    if "lossless" in intake and intake.get("lossless") is not True:
        reasons.append(f"intake.lossless={intake.get('lossless')!r} (must be true)")
    unaccounted = intake.get("unaccounted")
    if (
        isinstance(unaccounted, int)
        and not isinstance(unaccounted, bool)
        and unaccounted != 0
    ):
        reasons.append(f"intake.unaccounted={unaccounted} (must be 0)")
    eligible = intake.get("eligible_after_skips")
    originated = intake.get("originated")
    if (
        isinstance(eligible, int) and not isinstance(eligible, bool) and eligible > 0
        and isinstance(originated, int) and not isinstance(originated, bool)
        and originated == 0
    ):
        reasons.append(
            f"intake.eligible_after_skips={eligible} but intake.originated=0"
        )
    return "; ".join(reasons) if reasons else None


def check(root: Path, run_id: str, now: datetime) -> list[str]:
    """Every breach found for the expected session, as human-readable lines.

    Pure over its inputs (root's on-disk files + the clock) — no network, no
    side effects — so it is unit-testable against a fixture tree exactly like
    the other instruments' ``evaluate``/``decide`` cores. Empty list = accepted.
    """
    problems: list[str] = []
    session = expected_last_session(now)
    session_iso = session.isoformat()

    standouts_path = root / "site" / "factordata" / "us_standouts.json"
    standouts = _load_json(standouts_path)
    if not isinstance(standouts, dict):
        return [f"{standouts_path} missing or unreadable"]
    as_of = standouts.get("as_of")
    staleness = standouts.get("staleness")
    price_through = (
        staleness.get("price_through") if isinstance(staleness, dict) else None
    )
    if as_of != session_iso:
        problems.append(
            f"us_standouts.as_of={as_of!r} != expected session {session_iso!r}"
        )
    if price_through != as_of:
        problems.append(
            f"us_standouts.staleness.price_through={price_through!r} != "
            f"as_of={as_of!r}"
        )

    index_path = root / "site" / "prophet" / "index.json"
    index = _load_json(index_path)
    if not isinstance(index, dict):
        return problems + [f"{index_path} missing or unreadable"]

    if not isinstance(index.get("intake"), dict):
        problems.append(
            f"{index_path} carries no intake block — a genuine build regression, "
            "not a legacy-fixture shape (this script only ever runs against a "
            "live nightly's own fresh output)"
        )
    else:
        breach = intake_identity_breach(index.get("intake"))
        if breach:
            problems.append(f"intake identity: {breach}")

    plans = index.get("plans")
    plans = plans if isinstance(plans, list) else []
    cohort: list[dict] = []
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        recorded = str(plan.get("recorded_at") or "")[:10]
        if recorded != session_iso:
            continue
        cohort.append(plan)
        plan_id = plan.get("id")
        if not plan_id:
            problems.append(
                f"index plan recorded_at={session_iso} carries no id: {plan!r}"
            )
            continue
        plan_file = root / "site" / "prophet" / "plans" / f"{plan_id}.json"
        if not plan_file.is_file():
            problems.append(
                f"plan {plan_id} recorded for {session_iso} has no {plan_file}"
            )

    receipt_dir = root / "data" / "prophet" / "origination_receipts"
    receipts = (
        sorted(receipt_dir.glob(f"{run_id}-*.json")) if receipt_dir.is_dir() else []
    )
    originated_ids: set[str] = set()
    for receipt_path in receipts:
        doc = _load_json(receipt_path)
        if isinstance(doc, dict):
            originated_ids.update(str(i) for i in (doc.get("originated_plan_ids") or []))

    # A receipt is only OWED when this run's cohort is non-empty. The producer
    # ("Prophet nightly" step, scripts/build_prophet.py via daily.yml) legitimately
    # writes NO receipt on a night with zero new plans (`if not new_ids: raise
    # SystemExit(0)`) — an absent receipt on an honestly-empty night must never
    # become a false alarm.
    if cohort and not receipts:
        problems.append(
            f"{len(cohort)} plan(s) recorded for {session_iso} but no origination "
            f"receipt {receipt_dir}/{run_id}-*.json exists for this run "
            f"(run_id={run_id!r})"
        )

    for plan_id in sorted(originated_ids):
        plan_file = root / "site" / "prophet" / "plans" / f"{plan_id}.json"
        doc = _load_json(plan_file)
        if not isinstance(doc, dict) or not doc.get("recorded_at"):
            problems.append(
                f"plan {plan_id} originated this run (per receipt) carries no "
                "recorded_at stamp"
            )

    return problems


def _push_alert(message: str) -> None:
    """Best-effort engine/alert_triage.push_ops_alert, never fatal on its own.

    Unlike scripts/prophet_rescue.py (which deliberately avoids this import —
    see that module's docstring — because it must survive a broken engine
    tree from OUTSIDE it), this script runs INSIDE the engine job with the
    full venv already proven by every step ahead of it, so importing the real
    alert spine is the honest choice here rather than a second stdlib-only
    transport.
    """
    try:
        from engine.alert_triage import push_ops_alert  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(
            f"::warning title={ANNOTATION_TITLE}::push_ops_alert unavailable "
            f"({type(exc).__name__}: {exc}) — the ::error annotation above is the "
            "primary signal for this failure",
            flush=True,
        )
        return
    try:
        push_ops_alert(
            source="prophet_board_acceptance",
            type_="prophet_board_acceptance_failed",
            message=f"Prophet US board acceptance failed post-publish: {message}",
            severity="major",
        )
    except Exception as exc:  # noqa: BLE001 — the alarm must never crash the step
        print(
            f"::warning title={ANNOTATION_TITLE}::push_ops_alert raised "
            f"({type(exc).__name__}: {exc})",
            flush=True,
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Post-publish Prophet US board acceptance alarm (never a gate)"
    )
    ap.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    ap.add_argument("--now", default=None, help="ISO clock override (tests)")
    ap.add_argument("--root", default=str(REPO_ROOT))
    args = ap.parse_args(argv)

    if args.now:
        now = datetime.fromisoformat(args.now)
        now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    else:
        now = datetime.now(timezone.utc)
    root = Path(args.root)
    run_id = args.run_id or "unknown"

    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        print(
            f"::warning title={ANNOTATION_TITLE}::manual workflow_dispatch run — the "
            "schedule-only B1 candidate-episode reconcile step is skipped this run "
            "(this check does not gate or alter that step's trigger; the V4 program "
            "owns it)",
            flush=True,
        )

    problems = check(root, run_id, now)
    if problems:
        msg = "; ".join(problems)
        # Bare line-start print with flush=True — NEVER through a logger (house
        # law, tests/test_gh_annotation_line_start.py): every builder here logs
        # with a prefixing format, so a logger call would emit "WARNING ::error
        # …" and GitHub would silently drop the annotation.
        print(f"::error title={ANNOTATION_TITLE}::{msg}", flush=True)
        _push_alert(msg)
        return 1

    print(
        f"prophet-board-acceptance: OK for session {expected_last_session(now).isoformat()}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
