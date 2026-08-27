"""Prophet US permanence net — PR-1 (ROUTE: build, 2026-08-27 commission).

August 2026: the US Prophet Live 5-minute lane went dark 27 days with every
process signal green; boards were fresh while a mislabeled UI date read as
stale; the one instrument naming the board's exact path was warn-only exit-0;
pages routed to a dedup-gated webhook; prophet-outage issues sat unread five
days. An opus red-team of the first design found the fix had to be small,
ADDITIVE extensions of the existing instruments (scripts/freshness_sentinel.py,
scripts/check_nightly_liveness.py, scripts/prophet_rescue.py) plus one new
post-publish alarm (scripts/prophet_board_acceptance.py) — never a parallel
JSON-registry design.

This module pins the mechanism-agnostic coverage contract (the templates name
the artifacts a reader actually consumes; at least one grader must name each
one), the shared intake-identity predicate every instrument duplicates, the
acceptance script's own behaviors, the check_nightly_liveness lane-latch
acceptance exemption, and the freshness_sentinel heartbeat write/grade round
trip (plus its served-vs-R2 agreement check, R2 mocked).

NOT pinned here (see research/PROPHET_US_PERMANENCE_NET_2026-08-27.md §0 and
the commissioning packet's GAPS): the escalation ladder ([DAY N] title +
distinct alert type per day-level) and the self-withdraw cancel — both
withheld from this PR (see that masterplan and DEC-PROPHET-US-PERMANENCE-NET
for the specific conflicts that stopped them).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_nightly_liveness as nl  # noqa: E402
from scripts import freshness_sentinel as fs  # noqa: E402
from scripts import prophet_board_acceptance as pba  # noqa: E402
from scripts import prophet_rescue as pr  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. The mechanism-agnostic template-dereference coverage contract
# --------------------------------------------------------------------------- #
# The templates are the ground truth for what a reader actually consumes.
# Rather than hand-list "the artifacts that matter" (a list that rots the
# moment a template changes), this walks the three named template files for
# the artifact paths/variables they reference and asserts each is named by at
# least one grader among freshness_sentinel.SURFACES / check_nightly_liveness's
# own path constants. A future PR that adds a new consumed artifact to the
# templates without adding a grader for it fails THIS test, not a human's
# memory.
TEMPLATES = [
    ROOT / "templates" / "dashboard.html.j2",
    ROOT / "templates" / "_us_board_cards.html.j2",
    ROOT / "templates" / "_us_prophet_plan_cards.html.j2",
]


def _template_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in TEMPLATES if p.is_file())


def _all_grader_paths() -> set[str]:
    """Every artifact path named by a grader in this permanence net.

    freshness_sentinel.SURFACES carries explicit ``path`` keys (served/live/r2/
    page); check_nightly_liveness names site/prophet/index.json (Check C) and
    the per-market MARKET_BOARDS paths (Check D) as bare module constants
    rather than a SURFACES-shaped list, so both sources are unioned here.
    """
    paths = {s["path"] for s in fs.SURFACES}
    paths.add("site/prophet/index.json")          # check_nightly_liveness Check C
    for spec in nl.MARKET_BOARDS:
        paths.add(spec["path"])
    return paths


@pytest.mark.parametrize("template_path", TEMPLATES, ids=lambda p: p.name)
def test_every_named_template_exists(template_path: Path):
    """A missing template file would make the coverage contract below vacuously
    pass — pin its existence separately so that failure mode is loud."""
    assert template_path.is_file(), template_path


def test_us_standouts_referenced_by_the_template_is_graded():
    """dashboard.html.j2 reads the ``us_standouts`` context variable (the board
    of record, site/factordata/us_standouts.json) directly — PR-1 item 1a's
    whole reason for being. This is the artifact whose freeze (agreed board
    lag one layer above the Prophet plan index) no prior instrument named."""
    text = _template_text()
    assert "us_standouts" in text, "fixture template no longer references it?"
    graded = _all_grader_paths()
    assert "/factordata/us_standouts.json" in graded, (
        "us_standouts is consumed by templates/dashboard.html.j2 but no "
        f"grader names its path. Graded paths: {sorted(graded)}"
    )


def test_prophet_index_referenced_by_the_template_is_graded():
    """_us_prophet_plan_cards.html.j2 renders one .pvcard per
    site/prophet/index.json.plans row — the plan book itself."""
    text = _template_text()
    assert "site/prophet/index.json" in text
    graded = _all_grader_paths()
    assert "site/prophet/index.json" in graded or "/prophet/index.json" in graded, (
        f"prophet index is template-consumed but ungraded. Graded: {sorted(graded)}"
    )


def test_premium_payload_referenced_by_the_template_is_a_known_gap():
    """site/premiumdata/us_stocks.json (the paid card payload
    templates/_us_board_cards.html.j2 and _us_prophet_plan_cards.html.j2 both
    name) is NOT named by any grader in this PR. SCOPE items 1/2/3/4 never
    enumerated this artifact, so PR-1 does not add coverage for it — adding an
    uncommissioned SURFACES entry would be scope creep this packet's
    DEVIATIONS section flags instead. This test pins the gap as KNOWN rather
    than letting it hide: it must be revisited (`xfail`, not silently green)
    the day a future PR closes it, at which point flip this to the same
    shape as the two tests above.
    """
    text = _template_text()
    assert "premiumdata/us_stocks.json" in text, "fixture premise moved — re-check the templates"
    graded = _all_grader_paths()
    assert not any("premiumdata" in p for p in graded), (
        "premiumdata/us_stocks.json is now graded — flip this test to a "
        "positive coverage assertion like its us_standouts/prophet-index siblings"
    )


# --------------------------------------------------------------------------- #
# 2. The shared intake-identity predicate (duplicated across four instruments)
# --------------------------------------------------------------------------- #
# The healthy shape is the real 2026-08-25 site/prophet/index.json intake block
# (admitted 41 = 23 duplicate_id_blocked + 6 reorigination_blocked + 3
# validation_failed + 9 originated; unaccounted 0; lossless true).
HEALTHY_INTAKE = {
    "admitted": 41,
    "duplicate_id_blocked": 23,
    "reorigination_blocked": 6,
    "validation_failed": 3,
    "originated": 9,
    "eligible_after_skips": 12,
    "unaccounted": 0,
    "lossless": True,
}

INTAKE_PREDICATES = [
    ("freshness_sentinel", fs.intake_identity_breach),
    ("check_nightly_liveness", nl.intake_identity_breach),
    ("prophet_rescue", pr.intake_identity_breach),
    ("prophet_board_acceptance", pba.intake_identity_breach),
]


@pytest.mark.parametrize("name,predicate", INTAKE_PREDICATES, ids=[n for n, _ in INTAKE_PREDICATES])
def test_healthy_intake_shape_passes_in_every_instrument(name, predicate):
    assert predicate(HEALTHY_INTAKE) is None, name


@pytest.mark.parametrize("name,predicate", INTAKE_PREDICATES, ids=[n for n, _ in INTAKE_PREDICATES])
def test_a_wipeout_intake_fails_in_every_instrument(name, predicate):
    """lossless=False is the wipeout shape: the ledger admits it lost track."""
    wiped = dict(HEALTHY_INTAKE, lossless=False)
    breach = predicate(wiped)
    assert breach is not None, name
    assert "lossless" in breach, (name, breach)


@pytest.mark.parametrize("name,predicate", INTAKE_PREDICATES, ids=[n for n, _ in INTAKE_PREDICATES])
def test_unaccounted_above_zero_fails_in_every_instrument(name, predicate):
    unaccounted = dict(HEALTHY_INTAKE, unaccounted=2)
    breach = predicate(unaccounted)
    assert breach is not None, name
    assert "unaccounted" in breach, (name, breach)


@pytest.mark.parametrize("name,predicate", INTAKE_PREDICATES, ids=[n for n, _ in INTAKE_PREDICATES])
def test_eligible_candidates_with_zero_originated_fails_in_every_instrument(name, predicate):
    wedge = dict(HEALTHY_INTAKE, eligible_after_skips=12, originated=0)
    breach = predicate(wedge)
    assert breach is not None, name
    assert "originated" in breach, (name, breach)


@pytest.mark.parametrize("name,predicate", INTAKE_PREDICATES, ids=[n for n, _ in INTAKE_PREDICATES])
def test_an_entirely_absent_intake_abstains_rather_than_breaches(name, predicate):
    """Backward compatibility: every instrument's OWN pre-existing test fixtures
    predate this field. An absent/non-dict intake abstains (None), never
    breaches — the field's absence is reported (where it matters) by the
    caller's own explicit readability check, not by this predicate inventing
    text for a shape it cannot describe."""
    assert predicate(None) is None, name
    assert predicate({}) is None, name
    assert predicate("not a dict") is None, name


@pytest.mark.parametrize("name,predicate", INTAKE_PREDICATES, ids=[n for n, _ in INTAKE_PREDICATES])
def test_missing_lossless_key_abstains_rather_than_breaches(name, predicate):
    """A pre-PR-1 synthetic fixture that carries eligible_after_skips/originated
    but never modeled lossless/unaccounted (every existing decide()/evaluate()
    test fixture in this repo) must not spuriously start failing."""
    legacy = {"eligible_after_skips": 40, "originated": 25}
    assert predicate(legacy) is None, name


# --------------------------------------------------------------------------- #
# 3. recorded_at presence + acceptance-script behaviors
# --------------------------------------------------------------------------- #
def _write_json(path: Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _healthy_tree(root: Path, session: str = "2026-08-25", run_id: str = "999") -> None:
    _write_json(root / "site" / "factordata" / "us_standouts.json", {
        "as_of": session,
        "buy": [{"ticker": "AAPL"}],
        "lane_counts": {"live": 1},
        "staleness": {"price_through": session},
    })
    _write_json(root / "site" / "prophet" / "index.json", {
        "intake": HEALTHY_INTAKE,
        "plans": [
            {"id": "AAPL-BULL-20260825", "recorded_at": session},
        ],
    })
    _write_json(
        root / "site" / "prophet" / "plans" / "AAPL-BULL-20260825.json",
        {"id": "AAPL-BULL-20260825", "recorded_at": session, "asset": "AAPL"},
    )
    _write_json(
        root / "data" / "prophet" / "origination_receipts" / f"{run_id}-1-abcdef.json",
        {"originated_plan_ids": ["AAPL-BULL-20260825"]},
    )


def test_acceptance_script_accepts_a_fully_healthy_tree(tmp_path):
    _healthy_tree(tmp_path)
    problems = pba.check(tmp_path, "999", __import__("datetime").datetime(
        2026, 8, 25, 22, 0, tzinfo=__import__("datetime").timezone.utc
    ))
    assert problems == [], problems


def test_acceptance_script_flags_a_plan_recorded_but_never_originated(tmp_path):
    """recorded_at presence pin: a plan the run's receipt says it originated but
    that carries no recorded_at stamp on disk is a breach."""
    _healthy_tree(tmp_path)
    plan_path = tmp_path / "site" / "prophet" / "plans" / "AAPL-BULL-20260825.json"
    _write_json(plan_path, {"id": "AAPL-BULL-20260825", "asset": "AAPL"})  # no recorded_at
    problems = pba.check(tmp_path, "999", __import__("datetime").datetime(
        2026, 8, 25, 22, 0, tzinfo=__import__("datetime").timezone.utc
    ))
    assert any("recorded_at" in p for p in problems), problems


def test_acceptance_script_requires_a_receipt_only_when_the_cohort_is_non_empty(tmp_path):
    """A night with ZERO new plans legitimately writes no receipt at all
    (build_prophet's own `if not new_ids: raise SystemExit(0)`) — the acceptance
    script must not manufacture a false alarm out of an honestly-empty night."""
    import datetime as dt
    _write_json(tmp_path / "site" / "factordata" / "us_standouts.json", {
        "as_of": "2026-08-25", "buy": [{"ticker": "AAPL"}],
        "lane_counts": {"live": 1}, "staleness": {"price_through": "2026-08-25"},
    })
    _write_json(tmp_path / "site" / "prophet" / "index.json", {
        "intake": HEALTHY_INTAKE, "plans": [],
    })
    problems = pba.check(tmp_path, "999", dt.datetime(2026, 8, 25, 22, 0, tzinfo=dt.timezone.utc))
    assert not any("receipt" in p for p in problems), problems


def test_acceptance_script_flags_a_missing_receipt_when_the_cohort_is_non_empty(tmp_path):
    import datetime as dt
    _healthy_tree(tmp_path)
    # Delete the receipt this run should have written.
    for p in (tmp_path / "data" / "prophet" / "origination_receipts").glob("*.json"):
        p.unlink()
    problems = pba.check(tmp_path, "999", dt.datetime(2026, 8, 25, 22, 0, tzinfo=dt.timezone.utc))
    assert any("receipt" in p for p in problems), problems


def test_acceptance_script_flags_the_restamp_trap():
    """us_standouts.as_of == staleness.price_through is asserted independently of
    session matching — a rerun that re-stamps as_of while the priced content
    stays frozen must not go undetected."""
    import datetime as dt
    breach = pba.intake_identity_breach(HEALTHY_INTAKE)
    assert breach is None
    # as_of/price_through divergence is exercised through check(); build a tiny
    # tree by hand rather than reusing _healthy_tree so the divergence is explicit.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_json(root / "site" / "factordata" / "us_standouts.json", {
            "as_of": "2026-08-25", "buy": [{"ticker": "AAPL"}],
            "lane_counts": {"live": 1}, "staleness": {"price_through": "2020-01-01"},
        })
        _write_json(root / "site" / "prophet" / "index.json", {
            "intake": HEALTHY_INTAKE, "plans": [],
        })
        problems = pba.check(root, "999", dt.datetime(2026, 8, 25, 22, 0, tzinfo=dt.timezone.utc))
        assert any("price_through" in p for p in problems), problems


def test_acceptance_script_annotation_is_a_bare_line_start_print(tmp_path, capsys):
    """House law: any ::error/::warning must be a bare line-start print with
    flush=True — never through a logger. Exercise the real breach path (an
    empty tree) and assert the printed line's shape."""
    import datetime as dt
    rc = pba.main([
        "--root", str(tmp_path), "--run-id", "1",
        "--now", "2026-08-25T22:00:00+00:00",
    ])
    out = capsys.readouterr().out
    assert rc == 1
    error_lines = [ln for ln in out.splitlines() if "::error" in ln]
    assert error_lines, out
    for line in error_lines:
        assert line.startswith("::error"), line
        assert f"title={pba.ANNOTATION_TITLE}::" in line, line


def test_acceptance_script_warns_under_workflow_dispatch(tmp_path, monkeypatch, capsys):
    _healthy_tree(tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    rc = pba.main([
        "--root", str(tmp_path), "--run-id", "999",
        "--now", "2026-08-25T22:00:00+00:00",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    warn_lines = [ln for ln in out.splitlines() if "::warning" in ln]
    assert any("workflow_dispatch" in ln for ln in warn_lines), out
    for line in warn_lines:
        assert line.startswith("::warning"), line


# --------------------------------------------------------------------------- #
# 4. check_nightly_liveness lane-latch acceptance exemption (item 2c)
# --------------------------------------------------------------------------- #
def _no_success_state():
    import datetime as dt
    now = dt.datetime(2026, 8, 21, 8, 0, tzinfo=dt.timezone.utc)
    boundary = dt.datetime(2026, 8, 20, 22, 0, tzinfo=dt.timezone.utc)
    runs = [{
        "created_at": boundary.isoformat().replace("+00:00", "Z"),
        "status": "completed", "conclusion": "cancelled", "id": 1,
    }]
    index = {"source_asof": "2026-08-20"}     # data_current: src >= session (Thu)
    return runs, index, now


def test_lane_latch_downgrades_an_ordinary_no_success_run_to_a_warning():
    runs, index, now = _no_success_state()
    report = nl.evaluate(runs, index, now, acceptance_failed=False)
    assert not any("ACCEPTANCE FAILED" in f for f in report["fail_reasons"]), report
    assert any("LANE LATCH" in w for w in report["warnings"]), report


def test_lane_latch_exemption_keeps_an_acceptance_red_as_a_fail_reason():
    runs, index, now = _no_success_state()
    report = nl.evaluate(runs, index, now, acceptance_failed=True)
    assert any("ACCEPTANCE FAILED" in f for f in report["fail_reasons"]), report
    assert not any("LANE LATCH" in w for w in report["warnings"]), report
    assert report["ok"] is False


def test_job_failed_at_acceptance_step_requires_a_positive_match():
    assert nl.job_failed_at_acceptance_step(None) is False
    assert nl.job_failed_at_acceptance_step([]) is False
    assert nl.job_failed_at_acceptance_step([
        {"steps": [{"name": "prophet-board-acceptance (post-publish alarm, never a gate)",
                    "conclusion": "success"}]}
    ]) is False
    assert nl.job_failed_at_acceptance_step([
        {"steps": [{"name": "prophet-board-acceptance (post-publish alarm, never a gate)",
                    "conclusion": "failure"}]}
    ]) is True
    # A failure on an unrelated step must never trip the exemption.
    assert nl.job_failed_at_acceptance_step([
        {"steps": [{"name": "checkout", "conclusion": "failure"}]}
    ]) is False


def test_acceptance_step_marker_matches_the_producers_annotation_title():
    """Cross-file contract: check_nightly_liveness matches on the SAME string
    scripts/prophet_board_acceptance.py names its step/annotations with."""
    assert nl.ACCEPTANCE_STEP_MARKER == pba.ANNOTATION_TITLE


# --------------------------------------------------------------------------- #
# 5. freshness_sentinel heartbeat write + Check E grade round trip
# --------------------------------------------------------------------------- #
def test_heartbeat_written_by_a_pass_is_gradable_by_check_e(tmp_path):
    import datetime as dt

    def dead_served(served_dir, path):
        return fs.FetchResult(error="served read failed: no such file")

    now = dt.datetime(2026, 8, 25, 22, 0, tzinfo=dt.timezone.utc)
    fs.run(
        now=now, base="https://example.invalid", r2_base="https://example.invalid",
        public_dir=tmp_path / "public", state_dir=tmp_path / "state",
        fetcher=lambda url, *, want_body: fs.FetchResult(error="connection refused"),
        served_reader=dead_served,
    )
    staleness_path = tmp_path / "public" / "live" / "staleness.json"
    doc = json.loads(staleness_path.read_text())
    assert "heartbeat" in doc
    assert doc["heartbeat"]["last_pass_utc"] == now.isoformat()
    assert doc["heartbeat"]["cadence_minutes"] == 30.0
    assert isinstance(doc["heartbeat"]["surfaces"], dict) and doc["heartbeat"]["surfaces"]

    # Check E, fed the artifact this exact pass just wrote, at an instant well
    # inside the 90-minute (3-cadence) budget -> clean.
    fail, warn, facts = nl.evaluate_sentinel_heartbeat(doc, now + dt.timedelta(minutes=10))
    assert fail == [] and warn == [], (fail, warn)
    assert facts["sentinel_heartbeat_age_minutes"] == pytest.approx(10.0)


def test_check_e_pages_once_the_heartbeat_is_older_than_three_cadences():
    import datetime as dt
    now = dt.datetime(2026, 8, 25, 22, 0, tzinfo=dt.timezone.utc)
    doc = {"heartbeat": {"last_pass_utc": (now - dt.timedelta(minutes=95)).isoformat()}}
    fail, warn, facts = nl.evaluate_sentinel_heartbeat(doc, now)
    assert any("SENTINEL HEARTBEAT STALE" in f for f in fail), fail
    assert warn == []


def test_check_e_falls_back_to_generated_at_for_a_pre_pr1_sentinel_build():
    import datetime as dt
    now = dt.datetime(2026, 8, 25, 22, 0, tzinfo=dt.timezone.utc)
    doc = {"generated_at": (now - dt.timedelta(minutes=5)).isoformat()}  # no heartbeat key
    fail, warn, facts = nl.evaluate_sentinel_heartbeat(doc, now)
    assert fail == [] and warn == []
    assert facts["sentinel_heartbeat_age_minutes"] == pytest.approx(5.0)


def test_check_e_is_indeterminate_never_a_breach_on_an_unreadable_artifact():
    import datetime as dt
    fail, warn, facts = nl.evaluate_sentinel_heartbeat(None, dt.datetime.now(dt.timezone.utc))
    assert fail == []
    assert any("CHECK E INDETERMINATE" in w for w in warn), warn


def test_check_e_contributes_nothing_when_the_caller_never_asked():
    """Backward compatibility: every pre-PR-1 evaluate() caller in
    tests/test_nightly_liveness.py never mentions sentinel_heartbeat and must
    not retroactively gain a warning the day this check is added."""
    import datetime as dt
    fail, warn, facts = nl.evaluate_sentinel_heartbeat(
        nl._HEARTBEAT_NOT_REQUESTED, dt.datetime.now(dt.timezone.utc)
    )
    assert fail == [] and warn == [] and facts == {}


# --------------------------------------------------------------------------- #
# 6. prophet_live served-vs-R2 agreement (item 1c) — R2 mocked
# --------------------------------------------------------------------------- #
class _FakeR2Client:
    pass


def test_r2_agreement_degrades_to_a_warning_when_creds_are_absent(monkeypatch):
    from engine.prophet_live import r2io
    monkeypatch.setattr(r2io, "client", lambda: None)
    status, detail = fs.prophet_live_r2_agreement('{"meta": {"pass_ts": "x"}}',
                                                   __import__("datetime").datetime.now(
                                                       __import__("datetime").timezone.utc))
    assert status == "no_creds"
    assert detail is not None


def test_r2_agreement_is_ok_within_one_tick(monkeypatch):
    import datetime as dt
    from engine.prophet_live import r2io
    now = dt.datetime(2026, 8, 25, 20, 0, tzinfo=dt.timezone.utc)
    r2_pass_ts = (now - dt.timedelta(minutes=2)).isoformat()
    served_pass_ts = now.isoformat()
    monkeypatch.setattr(r2io, "client", lambda: _FakeR2Client())
    monkeypatch.setattr(
        r2io, "get_json",
        lambda key, s3=None, allow_public=True: {"meta": {"pass_ts": r2_pass_ts}},
    )
    served_body = json.dumps({"meta": {"pass_ts": served_pass_ts}})
    status, detail = fs.prophet_live_r2_agreement(served_body, now)
    assert status == "ok", detail


def test_r2_agreement_breaches_beyond_one_tick(monkeypatch):
    import datetime as dt
    from engine.prophet_live import r2io
    now = dt.datetime(2026, 8, 25, 20, 0, tzinfo=dt.timezone.utc)
    r2_pass_ts = (now - dt.timedelta(minutes=20)).isoformat()
    served_pass_ts = now.isoformat()
    monkeypatch.setattr(r2io, "client", lambda: _FakeR2Client())
    monkeypatch.setattr(
        r2io, "get_json",
        lambda key, s3=None, allow_public=True: {"meta": {"pass_ts": r2_pass_ts}},
    )
    served_body = json.dumps({"meta": {"pass_ts": served_pass_ts}})
    status, detail = fs.prophet_live_r2_agreement(served_body, now)
    assert status == "stale"
    assert "diverges" in detail


def test_r2_agreement_never_runs_for_a_surface_that_never_answered(tmp_path):
    """run() only attempts the R2 comparison when the served read itself
    succeeded — outside the live window or on a genuinely absent artifact
    there is nothing to compare, and the live-window gate already produced
    the right verdict."""
    import datetime as dt

    def served(served_dir, path):
        return fs.FetchResult(error="served read failed: no such file")

    now = dt.datetime(2026, 8, 8, 5, 0, tzinfo=dt.timezone.utc)  # window closed (Saturday)
    fs.run(
        now=now, base="https://example.invalid", r2_base="https://example.invalid",
        public_dir=tmp_path / "public", state_dir=tmp_path / "state",
        fetcher=lambda url, *, want_body: fs.FetchResult(error="connection refused"),
        served_reader=served,
    )
    doc = json.loads((tmp_path / "public" / "live" / "staleness.json").read_text())
    assert "r2_agreement" not in doc["surfaces"]["prophet_live"]


# --------------------------------------------------------------------------- #
# 7. prophet_rescue NO_COHORT extension (item 3a)
# --------------------------------------------------------------------------- #
def test_no_cohort_verdict_is_reused_not_duplicated_for_an_intake_breach():
    """FROZEN SPEC item 3a: extend NO_COHORT, never mint a new verdict name."""
    import datetime as dt
    now = dt.datetime(2026, 8, 21, 8, 40, tzinfo=dt.timezone.utc)
    session = dt.date(2026, 8, 20)
    index = {
        "source_asof": session.isoformat(),
        "plans": [{"id": "P1", "recorded_at": session.isoformat(), "asset": "AAPL"}],
        "intake": dict(HEALTHY_INTAKE, unaccounted=3),
    }
    state = pr.WatchdogState(
        now=now, main_index=index, r2_health=index,
        vps_status={"checks": {"site": {"commit_time": now.isoformat()}}},
        runs=[{"created_at": "2026-08-20T22:31:00Z", "status": "completed",
               "conclusion": "success", "id": 1, "html_url": "x", "event": "schedule"}],
        dispatch_runs_today=0,
    )
    actions = pr.decide(state)
    verdicts = {a.verdict for a in actions}
    assert pr.NO_COHORT in verdicts, actions
    breach_action = next(a for a in actions if a.verdict == pr.NO_COHORT)
    assert "intake identity" in breach_action.message


def test_stale_strand_issue_body_carries_the_ruleset_triage_line():
    """Item 3e: the STALE/STRAND issue template gains one triage line pointing
    at `gh api repos/{owner}/{repo}/rulesets` for the GH013-freeze class."""
    import datetime as dt
    now = dt.datetime(2026, 8, 21, 2, 0, tzinfo=dt.timezone.utc)
    action = pr.Action(pr.ALERT, pr.STALE, "the store is behind")
    state = pr.WatchdogState(
        now=now, main_index=None, r2_health=None, vps_status=None,
        runs=[], dispatch_runs_today=0,
    )
    body = pr.receipt([action], state, dt.date(2026, 8, 20), [])
    assert "rulesets" in body
    assert "GH013" in body
