"""tests/test_check_intelligence_registry.py — the gate must work in BOTH directions.

A validator that flags everything is as useless as one that flags nothing, so this suite
pins the guard's own selftest AND mutation-tests it: with the validator stubbed out, the
selftest must FAIL. Without that, the selftest is a receipt written from the same variable
it checks and cannot fail.

It also pins the two CI-observable behaviours the house laws depend on: annotations START
the line (a logger-prefixed one is dropped silently by GitHub), and the guard FAILS CLOSED
— a run that could not read an input says so on its summary line and exits NON-ZERO ON
EVERY RUN, with or without --strict (ruling 2026-08-14), instead of printing a
zero-violation count it did not earn.

NOTHING HERE ASSERTS ON LIVE CONTENT. There is no committed registry to compare against,
and no count from config/synapse.yml or data/qledger/ is pinned — both move without any PR
on this lane. Anything that needs a corpus with a KNOWN property (an unevidenced authority
artifact, a malformed store, an excluded cell) runs against
`check_intelligence_registry.write_fixture_root`, the same fixture source the guard's own
--selftest uses. `test_no_test_in_this_program_asserts_on_live_synapse_contents` enforces
that from inside, by AST, against a frozen allowlist of the tests that may touch the live
tree at all.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.check_intelligence_registry as guard
from engine.intelligence_registry import validate_overlay, validate_structure

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_intelligence_registry.py"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd or REPO),
        capture_output=True,
        text=True,
        check=False,
    )


def _selftest_rc() -> int:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return guard._selftest()


# ---------------------------------------------------------------------------
# The selftest itself
# ---------------------------------------------------------------------------

def test_selftest_passes_as_shipped():
    result = _run("--selftest")
    assert result.returncode == 0, result.stdout
    assert "selftest: PASS" in result.stdout


def test_selftest_covers_both_directions():
    result = _run("--selftest")
    assert "POSITIVE CONTROL" in result.stdout
    assert "NEGATIVE" in result.stdout
    # A FLOOR, NOT AN EQUALITY: adding a control must never require editing this line.
    # Re-based 2026-08-14 (60 -> 84, the count as shipped) so it measures something again.
    assert result.stdout.count("[PASS]") >= 84
    assert "[FAIL]" not in result.stdout


# ---------------------------------------------------------------------------
# MUTATION CONTROLS — the selftest must be able to fail
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,stub",
    [
        ("validate_structure accepts everything", ("validate_structure", lambda *a, **k: [])),
        ("validate_structure rejects everything", ("validate_structure", lambda *a, **k: ["x"])),
        ("validate_overlay accepts everything", ("validate_overlay", lambda *a, **k: [])),
        ("validate_overlay rejects everything", ("validate_overlay", lambda *a, **k: ["x"])),
        ("audit_content finds nothing", ("audit_content", lambda *a, **k: [])),
        ("resolve_qual_ladder_ref always resolves", ("resolve_qual_ladder_ref", lambda r, **k: "repo_path")),
    ],
)
def test_selftest_fails_when_the_validator_is_broken(monkeypatch, name, stub):
    """If any of these mutations still passes, the selftest is decorative."""
    attr, replacement = stub
    monkeypatch.setattr(guard, attr, replacement)
    assert _selftest_rc() == 1, f"selftest survived a broken validator: {name}"


def test_selftest_fails_when_the_C1_DERIVATION_ITSELF_IS_DELETED(monkeypatch):
    """THE NEGATIVE CONTROL THAT MATTERS. The other mutations stub the VALIDATORS; this one
    deletes the COMPUTATION the C-1 finding is made of — `unevidenced_artifacts` — inside
    the real build_registry, and the selftest must still fail.

    Without this, the selftest could be passing because its fixtures already contain the
    answer ("a receipt derived from what it checks cannot fail").
    """
    import engine.intelligence_registry as mod

    real_build = mod.build_registry

    def gutted(**kwargs):
        registry = real_build(**kwargs)
        for row in registry["engines"]:
            row["authority_evidence"]["unevidenced_artifacts"] = []
        return registry

    monkeypatch.setattr(guard, "build_registry", gutted)
    assert _selftest_rc() == 1, "the C-1 derivation is not covered by a negative control"


def test_selftest_fails_when_the_species_null_is_collapsed_to_an_empty_store(monkeypatch):
    """The 2026-08-12 failure, pinned. Substituting an EMPTY species list for the NULL is
    exactly 'could not look' rendered as 'looked and found nothing'; the selftest must see
    it."""
    import engine.intelligence_registry as mod

    real_build = mod.build_registry

    def collapsed(**kwargs):
        if kwargs.get("species") is None:
            kwargs["species"] = []
        return real_build(**kwargs)

    monkeypatch.setattr(guard, "build_registry", collapsed)
    assert _selftest_rc() == 1


def test_selftest_passes_again_once_restored():
    assert _selftest_rc() == 0


# ---------------------------------------------------------------------------
# Severity split — structural violations hard, content findings warn
# ---------------------------------------------------------------------------

def test_default_run_is_advisory_for_content_findings():
    """The content law fires on PRE-EXISTING corpus conditions no PR author caused. Wiring
    it hard on arrival would red main fleet-wide, which is how a gate gets routed around.

    ADVISORY COVERS FINDINGS **AND THE DATA PLANE** (ruling 2026-08-14, amended): only a
    PR-PLANE blind read or a structural violation reds without --strict.

    THE EXIT CODE IS ASSERTED AS A FUNCTION OF WHAT THIS SAME RUN REPORTED, not as a
    constant. `assert rc == 0` was an absolute claim about the live tree: one truncated
    line appended to data/qledger/claims.jsonl by the nightly falsified it, which is the
    defect class this suite exists to refuse. The ruling itself is pinned on fixture roots,
    where the inputs are controlled — see test_a_DATA_PLANE_blind_run_stays_advisory and
    test_a_PR_PLANE_blind_run_reds_without_strict.
    """
    result = _run("--json")  # non-strict: --json and plain return the same value
    payload = json.loads(result.stdout)
    expected = 1 if (payload["violations"] or payload["unreadable_by_plane"]["pr"]) else 0
    assert result.returncode == expected, payload


def test_strict_escalates_content_findings():
    """ONE SUBPROCESS. This compared the exit code of one invocation against the --json
    payload of a SECOND over the shared checkout — the cross-invocation race
    test_annotation_volume_is_budgeted was refactored to remove ("observed failing once in
    8 runs"). `--json --strict` yields both terms from the same process, so the two cannot
    disagree about which tree they saw."""
    result = _run("--json", "--strict")
    payload = json.loads(result.stdout)
    expected = 1 if (
        payload["violations"] or payload["findings"] or payload["unreadable_inputs"]
    ) else 0
    assert result.returncode == expected, payload


def test_structural_violations_exit_non_zero():
    """Proven on a synthetic bad view, not by hoping the live one is broken."""
    assert validate_structure({"schema": "wrong", "meta": {}, "engines": [], "excluded": []}) != []


# ---------------------------------------------------------------------------
# Annotation contract (CLAUDE.md §"GitHub annotations must START the line")
# ---------------------------------------------------------------------------

def test_annotations_start_the_line_and_are_never_logged(tmp_path):
    """ON A FIXTURE ROOT, which guarantees at least one annotation BY CONSTRUCTION.

    `assert annotated` against the live tree was a live NON-EMPTINESS assertion: the guard
    emits ::warning only for findings and blindness and ::error only for violations, so a
    tree with none of the three emits nothing at all — and that state is precisely T7's
    stated success condition (drain C-1, curate output_class, retire the weak heuristic).
    Succeeding at the program's goal must not red the lane that measures it. Same defect
    class as the `assert c1` this wave moved off the live corpus, one horizon further out.
    """
    root = guard.write_fixture_root(tmp_path / "repo")
    result = _run("--root", str(root))
    annotated = [
        line for line in result.stdout.splitlines()
        if "::warning" in line or "::error" in line or "::notice" in line
    ]
    assert annotated, "the fixture carries a C-1 finding, so an annotation is guaranteed"
    for line in annotated:
        assert line.startswith("::"), (
            f"annotation does not start the line — GitHub drops it silently: {line!r}"
        )


#: A corpus with NOTHING left to report — T7's stated success condition, in miniature. One
#: decorative display artifact: no authority, no ledger, no evaluated tier, so no C-1, no
#: OUTPUT_CLASS_MISSING, nothing.
_HEALED_SYNAPSE = """\
meta:
  schema_version: 1
artifacts:
  fixture-chip:
    path: site/fixture_chip.json
    format: json
    producer: engine/fixture_gate.py
    owner_program: fixture-prog
    cadence: daily-engine
    storage: git
    asof_field: asof
    freshness_sla_hours: 24
    schema: fixture
    tier: display
    horizon_role: context
    consumers: []
"""


def test_a_FULLY_HEALED_corpus_emits_no_annotation_and_still_exits_zero(tmp_path):
    """THE FORWARD PIN, and the reason two assertions moved off the live tree.

    `main()` emits ::error only for violations and ::warning only for findings and
    blindness, so a corpus with none of the three emits NOTHING — and that is exactly what
    T7 is trying to produce (drain C-1, curate output_class, retire the weak heuristic).
    Two tests asserted the live run emitted at least one annotation, which would have
    turned the program's success into this lane's red. Succeeding must be green, so it is
    pinned green here on a corpus that has already succeeded.
    """
    root = guard.write_fixture_root(tmp_path / "repo", synapse=_HEALED_SYNAPSE)
    result = _run("--root", str(root))
    assert result.returncode == 0, result.stdout
    annotated = [
        line for line in result.stdout.splitlines()
        if line.startswith("::warning") or line.startswith("::error")
    ]
    assert annotated == [], "a healed corpus must be silent, not merely quiet"
    assert "0 structural violation(s), 0 content finding(s), inputs=complete" in result.stdout


def test_guard_source_never_routes_an_annotation_through_a_logger():
    source = SCRIPT.read_text(encoding="utf-8")
    for bad in ('log.warning("::', 'log.error("::', 'logger.warning("::', 'logging.warning("::'):
        assert bad not in source


def _multi_engine_synapse(n: int) -> str:
    """A fixture synapse with `n` unevidenced scored cells — enough findings to COMPRESS.

    The compression half of the annotation budget needs several engines sharing one
    non-C-1 code; the single-cell default fixture cannot express that, and the live corpus
    must not be asked to (its finding count is exactly what T7 exists to drive to zero).
    """
    rows = [
        f"""\
  fixture-gate-{i}:
    path: data/fixture_gate_{i}.json
    format: json
    producer: engine/fixture_gate_{i}.py
    owner_program: fixture-prog
    cadence: daily-engine
    storage: git
    asof_field: asof
    freshness_sla_hours: 24
    schema: fixture
    tier: scored
    horizon_role: context
    consumers: []
"""
        for i in range(n)
    ]
    return "meta:\n  schema_version: 1\nartifacts:\n" + "".join(rows)


def test_annotation_volume_is_budgeted(tmp_path):
    """One annotation per finding would bury the actionable C-1 rows, so every non-C-1 code
    is aggregated to a single annotation with a count and full detail goes to stdout.

    THREE CHANNELS, NOT TWO. The budget covers per-engine C-1 rows, one aggregated count
    per other code, and — budgeted at EXACTLY ONE — the fail-closed COULD NOT LOOK line.
    The two-channel form of this assertion FORBADE the guard's own blindness annotation:
    any correctly-blind run emitted a third kind of ::warning and failed a test whose
    subject is annotation VOLUME. A test that reds when a guard fails closed is a test
    arguing for the guard to fail open, so the fix is here and never on the annotation.

    ON A FIXTURE ROOT with three unevidenced scored cells. `assert warnings` against the
    live tree was a live NON-EMPTINESS assertion — zero findings, zero violations and
    complete inputs emit no annotation at all, and that is T7's success condition, not a
    regression. The budget is a property of the guard's code, so it is provable on inputs
    this test owns.

    ONE SUBPROCESS. Comparing counts across TWO independent guard invocations was a
    cross-invocation equality assertion over a shared checkout — a racy structure, observed
    failing once in 8 runs. Reading both halves out of the SAME stdout removes the race by
    construction.
    """
    root = guard.write_fixture_root(tmp_path / "repo", synapse=_multi_engine_synapse(3))
    result = _run("--root", str(root))
    lines = result.stdout.splitlines()
    warnings = [line for line in lines if line.startswith("::warning")]
    per_engine = [w for w in warnings if "[AUTHORITY_WITHOUT_EVIDENCE]" in w]
    aggregated = [w for w in warnings if "engine(s) — detail on stdout" in w]
    blindness = [w for w in warnings if "COULD NOT LOOK" in w]
    assert warnings, result.stdout[-2000:]
    assert len(warnings) == len(per_engine) + len(aggregated) + len(blindness), (
        "every annotation is one C-1 row, one aggregated count, or the blindness line"
    )
    assert len(blindness) <= 1, (
        "the blindness channel is budgeted at exactly one line naming every missed input, "
        "never one per input"
    )
    detail_lines = [
        line for line in lines
        if line.startswith("  [") and "AUTHORITY_WITHOUT_EVIDENCE" not in line
    ]
    assert len(aggregated) < len(detail_lines), (
        "aggregation must actually compress — otherwise the budget is decorative"
    )


def test_the_blindness_annotation_is_inside_the_budget_on_a_BLIND_run(tmp_path):
    """The bucket above is unexercised on a healthy tree, where nothing is unreadable. Run
    the guard genuinely blind — one malformed line in a fixture claim store — and prove the
    third channel appears, stays at one line, and keeps the budget balanced."""
    root = guard.write_fixture_root(
        tmp_path / "repo", claims='{"desk": "d"}\n{not json\n'
    )
    result = _run("--root", str(root))
    warnings = [line for line in result.stdout.splitlines() if line.startswith("::warning")]
    per_engine = [w for w in warnings if "[AUTHORITY_WITHOUT_EVIDENCE]" in w]
    aggregated = [w for w in warnings if "engine(s) — detail on stdout" in w]
    blindness = [w for w in warnings if "COULD NOT LOOK" in w]
    assert len(blindness) == 1, result.stdout
    assert len(warnings) == len(per_engine) + len(aggregated) + len(blindness)


# ---------------------------------------------------------------------------
# FAIL CLOSED — "could not look" is never "looked and found nothing"
# ---------------------------------------------------------------------------

def test_an_unreadable_synapse_is_NOT_CHECKED_never_a_clean_count(tmp_path):
    """A previous round printed '0 integrity violation(s)' when it could not read its
    inputs. The SUMMARY LINE — the one line a CI reader sees — must say it could not look,
    and the run must exit non-zero."""
    result = _run("--root", str(tmp_path))
    assert result.returncode != 0, result.stdout
    summary = next(
        line for line in result.stdout.splitlines() if line.startswith("intelligence registry:")
    )
    assert "NOT CHECKED" in summary
    assert "inputs=INCOMPLETE" in summary
    # The normal-run summary shape must NOT appear: that is the sentence a CI reader skims
    # for, and printing it while blind is the whole defect.
    assert "structural violation(s)" not in summary
    assert "engines," not in summary
    assert any(line.startswith("::error") for line in result.stdout.splitlines())


def test_an_unreadable_synapse_in_json_mode_reports_absence_not_emptiness(tmp_path):
    result = _run("--root", str(tmp_path), "--json")
    payload = json.loads(result.stdout)
    assert payload["inputs_complete"] is False
    assert payload["violations"] is None and payload["findings"] is None, (
        "an empty list would render 'could not look' as 'looked and clean'"
    )
    assert payload["unreadable_inputs"] == ["config/synapse.yml"]
    assert result.returncode != 0


@pytest.mark.parametrize("argv", [[], ["--strict"], ["--json"], ["--json", "--strict"]])
def test_a_PARTIALLY_unreadable_input_set_names_what_it_missed_and_reds(monkeypatch, argv):
    """The other half of fail-closed: synapse READS but a downstream store does not.

    RULING 2026-08-14 — THIS REDS WITHOUT `--strict`, IN EVERY MODE. An incomplete read is
    a RUN-LEVEL defect (the guard failed to do its job), not a condition of the corpus, so
    it is not the kind of thing the advisory tier exists to soften. Gating it on a flag CI
    does not pass meant the fail-closed channel printed its warning and then returned the
    same exit code a clean run returns — the one signal an automated reader acts on.

    Both modes are parametrized on purpose: plain and --json compute their exit code in
    two places, and the previous shape let them disagree.
    """
    import scripts.build_intelligence_registry as builder

    real_build = builder.build

    def blinded(root):
        registry, report = real_build(root)
        report = dict(report)
        report["unreadable_inputs"] = list(report["unreadable_inputs"]) + [
            str(builder.SPECIES_REL)
        ]
        # data/species/registry.json is PR-plane — 17 commits in its whole history, every
        # one an adjudication PR — so this is the blindness the lane MAY red on.
        report["unreadable_by_plane"] = {
            "pr": list(report["unreadable_by_plane"]["pr"]) + [str(builder.SPECIES_REL)],
            "data": list(report["unreadable_by_plane"]["data"]),
        }
        report["inputs_complete"] = False
        return registry, report

    monkeypatch.setattr(guard, "build", blinded)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = guard.main(argv)
    out = buf.getvalue()
    assert rc != 0, f"a blind run must not exit 0 (argv={argv})"
    if "--json" in argv:
        payload = json.loads(out)
        assert payload["inputs_complete"] is False
        assert "data/species/registry.json" in payload["unreadable_inputs"]
    else:
        assert "inputs=INCOMPLETE" in out
        assert "data/species/registry.json" in out.split("intelligence registry:")[-1]


def test_a_DATA_PLANE_blind_run_is_REPRESENTED_but_stays_advisory(tmp_path):
    """B2 + THE JURISDICTION CUT, over real files.

    A claim store that OPENS but whose lines do not all parse used to be indistinguishable
    from one read cleanly with zero desk rows: the reader swallowed the JSONDecodeError,
    the report said `inputs=complete`, and the run exited 0 (B2). The first fix made it red
    unconditionally — which handed the nightly, the store's sole advancer, the power to red
    every PR in flight over one truncated line of 46,696. So it is REPRESENTED in full and
    GATED in the strict lane: the count is on the summary, the plane is named, the
    COULD NOT LOOK annotation fires, and the plain run stays advisory.
    """
    root = guard.write_fixture_root(
        tmp_path / "repo",
        claims='{"desk": "fixture_desk"}\n{not json\n[1, 2, 3]\n',
    )
    result = _run("--root", str(root))
    summary = next(
        line for line in result.stdout.splitlines() if line.startswith("intelligence registry:")
    )
    assert "inputs=INCOMPLETE" in summary
    assert "data-plane:" in summary and "PR-plane:" not in summary
    assert "claims.jsonl (2 unparseable line(s) of 3)" in result.stdout
    assert any("COULD NOT LOOK" in line for line in result.stdout.splitlines())
    assert result.returncode == 0, (
        "a nightly-advanced store must not red the PR lane: " + result.stdout[-1500:]
    )
    # BOTH MODES. The two exit codes are computed in two places and the previous shape let
    # them drift; --json is also what a consumer reads, so the plane must reach it.
    payload_run = _run("--root", str(root), "--json")
    payload = json.loads(payload_run.stdout)
    assert payload_run.returncode == 0
    assert payload["unreadable_by_plane"]["pr"] == []
    assert payload["unreadable_by_plane"]["data"] == payload["unreadable_inputs"]
    assert payload["inputs_complete"] is False


def test_the_SAME_data_plane_blindness_reds_under_strict(tmp_path):
    """The gate is DEFERRED to the strict lane, not deleted.

    ON A HEALED CORPUS, and that is load-bearing. Run against the default fixture this
    passes for the WRONG REASON: that corpus carries content findings, which --strict reds
    on by themselves, so the assertion held even with the data-plane term deleted from the
    exit expression (caught by mutation, 2026-08-14). With zero findings and zero
    violations, --strict can only red on the blind claim store.
    """
    root = guard.write_fixture_root(
        tmp_path / "repo",
        synapse=_HEALED_SYNAPSE,
        claims='{"desk": "fixture_desk"}\n{not json\n',
    )
    plain = _run("--root", str(root))
    assert plain.returncode == 0, plain.stdout
    assert "0 content finding(s)" in plain.stdout, (
        "the corpus must be healed, or --strict reds on findings and proves nothing"
    )
    assert _run("--root", str(root), "--strict").returncode == 1


@pytest.mark.parametrize(
    "override,why",
    [
        ({"species": "{ truncated"}, "species/registry.json moves only by adjudication PR"),
        ({"overlay": "{unclosed: ["}, "the curated overlay is hand-edited in a PR"),
        ({"qual_ladder": "- not\n- a mapping"}, "qual_ladder.yml is config"),
    ],
)
def test_a_PR_PLANE_blind_run_reds_without_strict(tmp_path, override, why):
    """The other side of the jurisdiction. Every one of these inputs moves ONLY through a
    pull request, so a PR author can cause the blindness and a PR author can fix it — the
    lane is entitled to red on it with no flag."""
    root = guard.write_fixture_root(tmp_path / "repo", **override)
    result = _run("--root", str(root))
    assert result.returncode == 1, why
    summary = next(
        line for line in result.stdout.splitlines() if line.startswith("intelligence registry:")
    )
    assert "PR-plane:" in summary, summary


def test_a_CLEAN_fixture_root_exits_zero(tmp_path):
    """THE POSITIVE HALF. Without it the test above passes for a guard that reds on
    everything, which is as useless as one that reds on nothing."""
    root = guard.write_fixture_root(tmp_path / "repo")
    result = _run("--root", str(root))
    assert result.returncode == 0, result.stdout
    assert "inputs=complete" in result.stdout


def test_C1_rows_are_printed_as_PLAIN_STDOUT_lines(tmp_path):
    """C-1 was annotation-only, so the law's primary deliverable was invisible to a
    terminal run, to a `| grep` and to anyone reading the raw job log instead of the
    Actions summary. The annotation budget re-ranks what GitHub renders; it must not decide
    what the LOG contains."""
    root = guard.write_fixture_root(tmp_path / "repo")
    result = _run("--root", str(root))
    plain = [
        line for line in result.stdout.splitlines()
        if line.startswith(f"  [AUTHORITY_WITHOUT_EVIDENCE] {guard.FIXTURE_ENGINE_ID}:")
    ]
    assert len(plain) == 1, result.stdout
    assert "qual_ladder_ref" in plain[0]


@pytest.mark.parametrize(
    "synapse,why",
    [
        ("{unclosed: [mapping\n", "does not parse as YAML"),
        ("- a\n- b\n", "parses to a list, not a mapping"),
    ],
)
def test_a_synapse_that_READS_but_does_not_PARSE_is_NOT_CHECKED(tmp_path, synapse, why):
    """A YAMLError used to escape as a bare traceback. A crashed gate reads exactly like an
    infrastructure failure in a job log, so it lands in the same NOT CHECKED + exit-1 path
    as an unreadable synapse — the message covers both."""
    root = guard.write_fixture_root(tmp_path / "repo", synapse=synapse)
    result = _run("--root", str(root))
    assert result.returncode != 0, why
    assert "Traceback" not in result.stderr, result.stderr[-2000:]
    summary = next(
        line for line in result.stdout.splitlines() if line.startswith("intelligence registry:")
    )
    assert "NOT CHECKED" in summary and "unreadable or unparseable" in summary


def test_an_unrelated_SystemExit_is_not_misattributed_by_the_sentinel_handler(monkeypatch):
    """The handler caught BARE `SystemExit` and unconditionally printed "config/synapse.yml
    is unreadable or unparseable" — so a `SystemExit` raised anywhere inside `build()`, at
    import time in a dependency say, would have produced a confident, specific and WRONG
    diagnosis. `_article2_modules` catches only `Exception`, so that path was reachable in
    principle. Keyed on the `SynapseUnavailable` sentinel, an unrelated exit now propagates
    as the crash it is: an honest crash beats a fluent misdiagnosis.
    """
    def exploding(root):
        raise SystemExit("an unrelated dependency called sys.exit() at import time")

    monkeypatch.setattr(guard, "build", exploding)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        with pytest.raises(SystemExit) as excinfo:
            guard.main([])
    assert "unrelated dependency" in str(excinfo.value)
    assert "config/synapse.yml is unreadable" not in buf.getvalue(), buf.getvalue()


def test_the_SENTINEL_itself_is_still_caught_and_reported(tmp_path):
    """The positive half: the sentinel path must keep working, or the fix above is just a
    hole with better manners."""
    root = guard.write_fixture_root(tmp_path / "repo", synapse="- not a mapping\n")
    result = _run("--root", str(root))
    assert result.returncode == 1
    assert "NOT CHECKED" in result.stdout
    assert issubclass(guard.builder.SynapseUnavailable, SystemExit)


def test_the_summary_line_always_carries_an_inputs_clause():
    result = _run()
    summary = [line for line in result.stdout.splitlines() if line.startswith("intelligence registry:")]
    assert len(summary) == 1, summary
    assert "inputs=" in summary[0]


def test_json_mode_always_emits_an_object():
    payload = json.loads(_run("--json").stdout)
    assert isinstance(payload, dict)
    assert "inputs_complete" in payload and "unreadable_inputs" in payload


# ---------------------------------------------------------------------------
# The C-1 backlog is VISIBLE and every row names its heal
# ---------------------------------------------------------------------------

def test_the_C1_backlog_is_reported_and_every_finding_names_its_heal(tmp_path):
    """ON A FIXTURE ROOT, NOT ON THE LIVE CORPUS. This asserted `c1` non-empty over the
    live tree, so DRAINING the C-1 backlog — the deliverable this whole law exists to
    produce, owned by T7 — would have reddened the lane that reports it. The property is
    about the DERIVATION (an authority-bearing artifact with no qual_ladder_ref is
    reported, and the finding names its heal), so it belongs on an input that contains one
    by construction.

    The fixture comes from the guard's own `write_fixture_root`, the same source its
    --selftest uses; a parallel fixture corpus here is how two definitions of the exemplar
    drift apart.
    """
    root = guard.write_fixture_root(tmp_path / "repo")
    payload = json.loads(_run("--root", str(root), "--json").stdout)
    c1 = [f for f in payload["findings"] if f["code"] == "AUTHORITY_WITHOUT_EVIDENCE"]
    assert c1, "an unevidenced authority artifact must be reported, not hidden"
    assert {f["engine_id"] for f in c1} == {guard.FIXTURE_ENGINE_ID}
    for finding in c1:
        assert "qual_ladder_ref" in finding["detail"], "every finding names its heal"


def test_the_derived_view_has_zero_structural_violations():
    """Structural violations are properties of the DERIVATION and of the hand-edited
    overlay — green by construction on arrival, so they can be hard without firing
    fleet-wide for nobody's fault."""
    payload = json.loads(_run("--json").stdout)
    assert payload["violations"] == [], payload["violations"]


# ---------------------------------------------------------------------------
# Overlay orphan rule
# ---------------------------------------------------------------------------

def test_orphan_overlay_row_is_a_hard_error_not_a_warning():
    violations = validate_overlay(
        {"schema_version": 1, "engines": {"gone/away.py::prog": {"not_an_engine": {"reason": "r"}}}},
        ["engine/a.py::prog"],
    )
    assert any("orphan" in v for v in violations)


def test_overlay_forbidden_key_names_the_dnr_row():
    violations = validate_overlay(
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"authority": "gate_size"}}},
        ["engine/a.py::prog"],
    )
    assert any("KILL-PARALLEL-KNOWLEDGE-BASE" in v for v in violations)


def test_the_overlay_orphan_rule_reads_the_PARTITION_not_the_built_ids(tmp_path):
    """A `not_an_engine` row used to SELF-LEGITIMATE: it created the excluded row that
    proved it was not an orphan, so the orphan rule could never fire on it.

    ON A FIXTURE ROOT. This ran `build(REPO)` and asserted the LIVE tree contains at least
    one excluded cell — a fact a sibling PR editing config/synapse.yml owns, not this lane.
    The fixture carries a `<MANUAL>` placeholder producer, so the derived exclusion exists
    BY CONSTRUCTION and the three properties are provable rather than borrowed.
    """
    from scripts.build_intelligence_registry import build as build_view

    root = guard.write_fixture_root(tmp_path / "repo")
    registry, report = build_view(root)
    excluded_ids = {r["engine_id"] for r in registry["excluded"]}
    assert excluded_ids == {guard.FIXTURE_EXCLUDED_ENGINE_ID}
    assert excluded_ids <= set(report["cell_ids"]), (
        "cell_ids is the PRE-EXCLUSION partition, so an excluded id is still a real cell"
    )
    assert guard.FIXTURE_EXCLUDED_ENGINE_ID not in {
        r["engine_id"] for r in registry["engines"]
    }, "the excluded cell must be absent from the BUILT ids — that is the gap it exploited"
    assert validate_overlay(
        {"schema_version": 1, "engines": {"engine/ghost.py::nowhere": {"not_an_engine": {
            "reason": "x" * 50, "ratified_by": "y", "date": "2026-08-12"}}}},
        report["cell_ids"],
    ), "a row for a cell the partition does not contain must still be an orphan"


# ---------------------------------------------------------------------------
# There is no equality pin left to red the fleet
# ---------------------------------------------------------------------------

def test_the_guard_has_no_drift_or_equality_mode():
    """Rounds 1 and 2 both shipped an equality pin and both were scheduled fleet-wide
    reds. Their absence is the architecture, so it is asserted FUNCTIONALLY — the prose in
    both modules discusses the deleted pin by name, so a grep of the source text would
    match its own postmortem."""
    assert _run("--check").returncode == 2, "--check must be an unknown argument"

    # ...and nothing in the program OPENS a generated artifact.
    for module in (SCRIPT, REPO / "scripts" / "build_intelligence_registry.py",
                   REPO / "engine" / "intelligence_registry.py"):
        source = module.read_text(encoding="utf-8")
        for reader in ('read_text(', 'json.load(', 'open('):
            for line in source.splitlines():
                if reader in line and "intelligence_registry.json" in line:
                    raise AssertionError(f"{module.name}: reads a generated artifact: {line}")


# ---------------------------------------------------------------------------
# THE META-TEST — which tests are allowed to touch the LIVE tree at all
# ---------------------------------------------------------------------------

#: Every test in this program that invokes the guard or the builder against the LIVE tree,
#: each with the reason it is allowed to. Set equality is asserted in BOTH directions, so
#: adding a live-invoking test AND silently removing one are both caught.
_LIVE_INVOKING_ALLOWLIST = frozenset({
    # --selftest never opens the live tree at all: it derives in memory and, since
    # 2026-08-14, over throwaway fixture roots under the system temp dir.
    "test_selftest_passes_as_shipped",
    "test_selftest_covers_both_directions",
    # Shape-only: the exit code must equal the RULING applied to what this same run
    # reported about itself. No count, no name, and nothing a nightly append can falsify.
    "test_default_run_is_advisory_for_content_findings",
    # Shape-only: same structure under --strict, from ONE invocation.
    "test_strict_escalates_content_findings",
    # Shape-only: monkeypatches the REPORT before main() ever sees it, so it asserts
    # nothing whatever about the live tree — but `guard.main(argv)` IS a live entry point
    # and the detector must see it, so it is listed rather than invisible.
    "test_a_PARTIALLY_unreadable_input_set_names_what_it_missed_and_reds",
    # Shape-only, and it never reaches the tree at all: `build` is replaced by a stub that
    # raises. Listed for the same reason — `guard.main([])` is a live entry point, and an
    # entry point the detector cannot see is how this allowlist stopped being the set it
    # claimed to be.
    "test_an_unrelated_SystemExit_is_not_misattributed_by_the_sentinel_handler",
    # Shape-only: exactly one summary line, and it carries an `inputs=` clause.
    "test_the_summary_line_always_carries_an_inputs_clause",
    # Shape-only: --json emits an object with the two fail-closed keys.
    "test_json_mode_always_emits_an_object",
    # LIVE CONTENT ON PURPOSE, and it is the gate working. Structural violations are
    # PR-CAUSED and hard by design — green by construction on arrival — so a sibling PR
    # that introduces one SHOULD red this lane. That is the one thing this program is
    # allowed to be strict about against the real corpus.
    "test_the_derived_view_has_zero_structural_violations",
    # Shape-only: argparse rejects `--check` with rc 2 before any input is read. The pin is
    # on the ABSENCE of the equality mode, which is the architecture.
    "test_the_guard_has_no_drift_or_equality_mode",
    # Live-input SHAPE only: the builder does not crash, the view is well-formed, and the
    # partition is total. No count, no name, no value.
    "test_the_builder_runs_over_the_live_tree_and_returns_a_well_formed_view",
    "test_the_live_view_is_idempotent_within_one_snapshot",
    "test_content_audit_is_pure_over_a_loaded_registry",
    # The shipped overlay must obey the four-key allowlist and name only real cells —
    # a property of the hand-edited file, not of the corpus it is keyed against.
    "test_the_shipped_overlay_is_structurally_valid_against_the_partition",
    # THE VOLATILITY SIMULATIONS. Each builds the live view TWICE and asserts the two are
    # equivalent across a synthetic append. Every assertion is a DIFFERENCE between the two
    # builds — a new desk appeared; the engine set and the finding set did not move — so
    # whatever the live corpus already holds appears on both sides and cancels. Neither
    # asserts an ABSOLUTE property of the live tree; the malformed-append case did, and
    # that is exactly why it moved to a fixture root (a truncated line in the live claim
    # store must not be able to red a T1 test).
    "test_a_nightly_CLAIM_APPEND_invalidates_nothing",
    "test_a_SIBLING_PR_adding_a_synapse_artifact_invalidates_nothing",
})


#: Modules whose entry points reach the live tree when handed no explicit root.
_T1_MODULES = frozenset({
    "scripts.check_intelligence_registry", "scripts.build_intelligence_registry",
})
#: Entry points that DEFAULT to the repo root, so "no --root" means "live".
_ROOT_DEFAULTING_ENTRIES = frozenset({"main", "_run"})
#: Entry points that take the root POSITIONALLY, so "an argument mentioning REPO" is live.
_ROOT_ARGUMENT_ENTRIES = frozenset({"build"})
#: CLI filenames whose direct `subprocess.run` is a live invocation without `--root`.
_T1_CLI_BASENAMES = ("check_intelligence_registry.py", "build_intelligence_registry.py")


def _t1_aliases(tree: ast.AST) -> tuple[set[str], set[str], set[str]]:
    """Resolve every local name that can reach a T1 entry point.

    Returns (module aliases, root-defaulting entry aliases, root-argument entry aliases).

    ALIAS RESOLUTION IS THE POINT. Matching two literal names missed
    ``from … import build as build_view`` — the alias this very file uses — and
    ``guard.main(...)``, the in-process entry its own fail-closed tests call. Both were
    LIVE, both invisible, and one was already committed and unlisted. Imports are collected
    from the WHOLE tree, function bodies included, because these suites import inside test
    functions; that is over-inclusive by construction, which is the safe direction for a
    detector whose failure mode is silence.
    """
    modules: set[str] = set()
    defaulting: set[str] = set(_ROOT_DEFAULTING_ENTRIES)
    positional: set[str] = set(_ROOT_ARGUMENT_ENTRIES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _T1_MODULES:
                    modules.add(alias.asname or alias.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom):
            if node.module in _T1_MODULES:
                for alias in node.names:
                    local = alias.asname or alias.name
                    if alias.name in _ROOT_DEFAULTING_ENTRIES:
                        defaulting.add(local)
                    elif alias.name in _ROOT_ARGUMENT_ENTRIES:
                        positional.add(local)
            elif node.module == "scripts":
                for alias in node.names:
                    if f"scripts.{alias.name}" in _T1_MODULES:
                        modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
            # `runner = _run` — a rename is an alias too.
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if node.value.id in defaulting:
                        defaulting.add(target.id)
                    elif node.value.id in positional:
                        positional.add(target.id)
    return modules, defaulting, positional


def _callee_name(func: ast.expr, modules: set[str]) -> str | None:
    """The entry-point name a call expression resolves to, or None.

    Handles the bare name, the attribute form on a known module alias, and
    ``getattr(<module alias>, "<entry>")`` — the last because it was demonstrated as an
    evasion, not because anyone writes it on purpose.
    """
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        owner = func.value
        if isinstance(owner, ast.Name) and owner.id in modules:
            return func.attr
        return func.attr
    if (
        isinstance(func, ast.Call)
        and isinstance(func.func, ast.Name)
        and func.func.id == "getattr"
        and len(func.args) == 2
        and isinstance(func.args[0], ast.Name)
        and func.args[0].id in modules
        and isinstance(func.args[1], ast.Constant)
    ):
        return str(func.args[1].value)
    return None


def _mentions_root_flag(args: list[ast.expr]) -> bool:
    """True when a ``"--root"`` string constant appears anywhere in the arguments.

    Walks INTO list/tuple literals, because the in-process entry takes an argv LIST. An
    argv that is not a literal (a parameter, a fixture) yields False and the call counts as
    LIVE — fail-closed: a detector that guesses "probably rooted" is the one that goes
    silent.
    """
    return any(
        isinstance(sub, ast.Constant) and sub.value == "--root"
        for arg in args
        for sub in ast.walk(arg)
    )


def _is_t1_cli_subprocess(call: ast.Call, name: str | None) -> bool:
    """A direct ``subprocess.run([... 'check_intelligence_registry.py' ...])``."""
    if name != "run":
        return False
    text = " ".join(
        str(sub.value)
        for sub in ast.walk(call)
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
    )
    return any(cli in text for cli in _T1_CLI_BASENAMES)


def _live_invoking_tests(source: str) -> set[str]:
    """Names of `test_*` functions that reach the live tree, by AST.

    FOUR SHAPES, every one of them measured from a real or demonstrated evasion:

      (a) a ROOT-DEFAULTING entry — ``_run(...)``, ``main(...)``, ``<guard>.main(...)`` —
          with no ``"--root"`` string constant among its arguments. These default to the
          repo root, so the absence of the flag IS the live invocation.
      (b) a ROOT-ARGUMENT entry — ``build(...)`` / ``<mod>.build(...)`` — with an argument
          expression that mentions ``REPO``.
      (c) either of the above reached through an ALIAS: ``import … as``,
          ``from … import x as y``, a plain rename, or ``getattr(mod, "main")``.
      (d) a direct ``subprocess.run`` naming either CLI, with no ``"--root"`` constant.

    SCOPE, stated rather than implied: live reads through builder INTERNALS
    (``_scan_producers(REPO, …)``, ``_load_species(REPO)``, ``_tracked_file_exists(REPO,
    …)``) are still not matched. They are shape-only by construction — they assert that a
    read resolves, never what it returned — and widening to "any call mentioning REPO"
    would swallow ``(REPO / "tests" / name).read_text()`` and turn the allowlist into a
    list of every test in the file. The string-needle layer in the caller covers the
    remaining shape (a direct read of the corpus path).
    """
    tree = ast.parse(source)
    modules, defaulting, positional = _t1_aliases(tree)
    live: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
            name = _callee_name(call.func, modules)
            args = [*call.args, *(kw.value for kw in call.keywords)]
            if name in defaulting and not _mentions_root_flag(args):
                live.add(node.name)
            elif name in positional and any(
                any(isinstance(sub, ast.Name) and sub.id == "REPO" for sub in ast.walk(arg))
                for arg in args
            ):
                live.add(node.name)
            elif _is_t1_cli_subprocess(call, name) and not _mentions_root_flag(args):
                live.add(node.name)
    return live


def test_no_test_in_this_program_asserts_on_live_synapse_contents():
    """THE STANDING RULE, ENFORCED FROM INSIDE. A sibling PR adding a scored artifact to
    config/synapse.yml must never red this lane, so no test may assert on what that file
    contains. Live-input tests go through the builder and assert only shape.

    THE NEEDLE GREP THIS REPLACED SAW NEITHER REAL CALL SHAPE. It banned a direct
    read-call on the corpus filename plus two naming conventions, and both of the actual
    live invocations in these suites — a `_run()` subprocess with no `--root`, and
    `build(REPO)` — sailed past it. It reported clean while two tests asserted on live
    corpus contents. The rule is now structural: parse both suites, derive the
    live-invoking set, and pin it against an allowlist by SET EQUALITY, so a new live
    invocation and a silently deleted one are both failures.

    The string needles are kept as a second, independent layer and are still ASSEMBLED AT
    RUNTIME so this file does not contain them literally — a self-matching guard reports
    its own definition and can never be green.
    """
    live: set[str] = set()
    corpus = "synapse.yml"
    needles = [
        corpus + '").read_text',
        corpus + "').read_text",
        "def " + "live_synapse",
        "live_" + "registry",
    ]
    for name in ("test_intelligence_registry.py", "test_check_intelligence_registry.py"):
        source = (REPO / "tests" / name).read_text(encoding="utf-8")
        for banned in needles:
            assert banned not in source, f"{name}: reads live corpus contents ({banned})"
        live |= _live_invoking_tests(source)

    assert live == set(_LIVE_INVOKING_ALLOWLIST), (
        "the set of tests that reach the LIVE tree changed. Added: "
        f"{sorted(live - _LIVE_INVOKING_ALLOWLIST)}; removed: "
        f"{sorted(_LIVE_INVOKING_ALLOWLIST - live)}. Every entry needs a one-line "
        "justification for why it is shape-only (or, for the structural-violation test, "
        "why live content IS the intent)."
    )


#: ONE CANNED SNIPPET PER EVASIVE SHAPE. Every entry the reviewer demonstrated the old
#: two-name rule sliding past is here, beside the legal counterpart that must stay clean —
#: the control is what proves the detector SEES each shape, and a detector without one is
#: how the previous rule shipped green and blind.
_DETECTOR_FIXTURE = """\
import subprocess
import scripts.check_intelligence_registry as g
import scripts.build_intelligence_registry as builder
from scripts.build_intelligence_registry import build as build_view
from scripts.check_intelligence_registry import main as guard_main
REPO = 1

def test_bare_run():
    _run()

def test_json_run():
    _run('--json')

def test_module_attr_main():
    g.main(['--json'])

def test_imported_main_alias():
    guard_main([])

def test_nonconstant_argv():
    g.main(argv)

def test_build_alias_on_repo():
    build_view(REPO)

def test_builder_dot_build_repo():
    builder.build(REPO)

def test_renamed_runner():
    runner = _run
    runner()

def test_getattr_evasion():
    getattr(g, 'main')([])

def test_direct_subprocess():
    subprocess.run([sys.executable, 'scripts/check_intelligence_registry.py'])

def test_rooted_run():
    _run('--root', str(tmp_path))

def test_rooted_main():
    g.main(['--root', str(tmp_path), '--json'])

def test_build_fixture():
    build(tmp_path / 'repo')

def test_build_alias_fixture():
    build_view(tmp_path / 'repo')

def test_rooted_subprocess():
    subprocess.run([sys.executable, 'scripts/check_intelligence_registry.py', '--root', str(p)])

def test_unrelated_subprocess():
    subprocess.run(['git', 'ls-files', 'data/intelligence_registry.json'])

def _helper_is_not_a_test():
    _run()
"""

#: The shapes that MUST be flagged. Everything else in the fixture must stay clean.
_DETECTOR_EXPECTED = {
    "test_bare_run",              # (a) root-defaulting helper, no --root
    "test_json_run",              # (a) …with an unrelated flag
    "test_module_attr_main",      # (a)+(c) attribute form on a module alias
    "test_imported_main_alias",   # (c) `from … import main as guard_main`
    "test_nonconstant_argv",      # (a) non-literal argv is LIVE, fail-closed
    "test_build_alias_on_repo",   # (c) `build as build_view` — the alias this file uses
    "test_builder_dot_build_repo",  # (b) attribute form of the root-argument entry
    "test_renamed_runner",        # (c) plain rename
    "test_getattr_evasion",       # (c) getattr indirection
    "test_direct_subprocess",     # (d) the CLI by path, no --root
}


def test_the_meta_test_can_actually_see_every_live_call_shape():
    """THE CONTROL THAT MATTERS. The rule this replaced was green while blind — it matched
    two literal names and slid past six real shapes, two of which the surrounding file
    actively teaches (`build as build_view`, `guard.main(...)`). Each is now a canned
    snippet here, paired with the `--root`/fixture counterpart that must stay clean, so the
    detector's coverage is asserted rather than assumed."""
    seen = _live_invoking_tests(_DETECTOR_FIXTURE)
    assert seen == _DETECTOR_EXPECTED, (
        f"missed: {sorted(_DETECTOR_EXPECTED - seen)}; "
        f"false positives: {sorted(seen - _DETECTOR_EXPECTED)}"
    )
