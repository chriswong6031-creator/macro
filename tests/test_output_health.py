"""tests/test_output_health.py — the Eval OS T4 acceptance suite (output health).

FIXTURE ROOTS ONLY. Nothing here asserts on live ``config/synapse.yml`` content or on the
live estate's health: the corpus took 69 commits in the trailing 14 days, and "the estate
is stale tonight" is operational data, not a PR defect. Every scenario is built in memory
or under ``tmp_path``, so a sibling PR editing the registry — or a genuinely stale
artifact — can never red this lane.

THREE OF THESE TESTS ARE MUTATION TARGETS (18/19/20 of the commission). They are named
``test_mutation_*`` so the receipt is unambiguous: break the rule in
``engine/output_health.py``, run the named test, watch it fail, restore.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import scripts.build_output_health as CLI  # noqa: E402
from engine import output_health as OH  # noqa: E402
from engine.neuralweb.synapse import validate_registry  # noqa: E402
from lib.dataos.temporal import TemporalError  # noqa: E402

NOW = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)
FRESH = "2026-08-14T06:00:00+00:00"      # 6h before NOW — inside a 24h SLA
OLD = "2026-08-01T06:00:00+00:00"        # 318h before NOW — far outside it

PRODUCER_A = "engine/a.py"
PRODUCER_B = "engine/b.py"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def artifact(
    path: str,
    *,
    producer: str,
    consumers: tuple[str, ...] = (),
    asof_field: str | None = "asof",
    sla: int | None = 24,
    storage: str = "git",
    fmt: str = "json",
    owner: str = "test-program",
    **extra: object,
) -> dict:
    entry: dict = {
        "path": path,
        "format": fmt,
        "producer": producer,
        "owner_program": owner,
        "cadence": "daily-engine",
        "storage": storage,
        "asof_field": asof_field,
        "freshness_sla_hours": sla,
        "schema": "none",
        "tier": "display",
        "horizon_role": "context",
        "weights": "none",
        "consumers": list(consumers),
    }
    entry.update(extra)
    return entry


def synapse_doc(**artifacts: dict) -> dict:
    return {
        "meta": {
            "schema_version": 1,
            "description": "fixture",
            "tier_vocabulary": {},
            "article2_surfaces": [],
        },
        "artifacts": dict(artifacts),
    }


def registry_for(
    doc: dict, *, output_class: str | None = None, excluded_cells: tuple[str, ...] = ()
) -> dict:
    """A minimal stand-in for the T1 view: the shape the resolver joins against."""
    cells: dict[str, list[str]] = {}
    for aid, entry in doc["artifacts"].items():
        eid = f"{entry['producer']}::{entry['owner_program']}"
        cells.setdefault(eid, []).append(aid)
    engines, excluded = [], []
    for eid, aids in sorted(cells.items()):
        if eid in excluded_cells:
            excluded.append(
                {
                    "engine_id": eid,
                    "artifacts": sorted(aids),
                    "reason": "derived: fixture exclusion",
                    "would_be_artifact_authorities": ["display"],
                }
            )
            continue
        engines.append(
            {
                "engine_id": eid,
                "output_class": output_class,
                "artifacts": [
                    {"id": aid, "artifact_authority": "display"} for aid in sorted(aids)
                ],
            }
        )
    return {"schema": "intelligence_registry.v1", "engines": engines, "excluded": excluded}


def obs(exists: bool | None = True, asof: str | None = FRESH, **extra: object) -> dict:
    row: dict = {
        "exists": exists,
        "presence_source": "filesystem" if exists is not None else None,
        "content_asof_raw": asof,
        "asof_field_present": None if asof is None else True,
        "watermark_field_used": None if asof is None else "asof",
        "mtime_utc": None,
        "mtime_trusted": False,
        "parse_error": None,
        "sparse_unmaterialized": False,
    }
    row.update(extra)
    return row


def two_artifact_estate(**a_extra: object) -> dict:
    """``b`` flows into ``a``: b lists a's producer among its consumers."""
    return synapse_doc(
        a=artifact("data/a.json", producer=PRODUCER_A, **a_extra),
        b=artifact("data/b.json", producer=PRODUCER_B, consumers=(PRODUCER_A,)),
    )


def resolve(doc: dict, observations: dict, **kwargs) -> dict:
    view = OH.resolve_output_health(
        synapse=doc,
        registry=kwargs.pop("registry", None) or registry_for(doc),
        observations=observations,
        now=kwargs.pop("now", NOW),
        **kwargs,
    )
    return {row["artifact_id"]: row for row in view["outputs"]}


# ---------------------------------------------------------------------------
# 1-8 — the core ladder
# ---------------------------------------------------------------------------

def test_01_current_output_with_current_inputs_is_healthy():
    doc = two_artifact_estate()
    rows = resolve(doc, {"a": obs(), "b": obs()})
    assert rows["a"]["state"] == "healthy"
    assert rows["a"]["assessment_status"] == "complete"
    assert rows["a"]["decided_by"] == "content_watermark"
    assert rows["a"]["required_inputs"] == [
        {"artifact_id": "b", "state": "healthy", "assessment_status": "complete"}
    ]


def test_02_optional_stale_input_degrades():
    doc = two_artifact_estate(
        health_optional_upstreams=["b"], notes="b is a nice-to-have overlay"
    )
    rows = resolve(doc, {"a": obs(), "b": obs(asof=OLD)})
    assert rows["b"]["state"] == "stale"
    assert rows["a"]["state"] == "degraded"
    assert "optional_input_stale:b" in rows["a"]["reason_codes"]
    assert rows["a"]["required_inputs"] == []


def test_03_optional_missing_input_degrades():
    doc = two_artifact_estate(
        health_optional_upstreams=["b"], notes="b is a nice-to-have overlay"
    )
    rows = resolve(doc, {"a": obs(), "b": obs(exists=False, asof=None)})
    assert rows["b"]["state"] == "unavailable"
    assert rows["a"]["state"] == "degraded"
    assert "optional_input_missing:b" in rows["a"]["reason_codes"]


def test_04_required_degraded_input_degrades():
    doc = two_artifact_estate()
    rows = resolve(
        doc,
        {"a": obs(), "b": obs()},
        self_health={"b": {"source": "fixture", "status": "degraded"}},
    )
    assert rows["b"]["state"] == "degraded"
    assert rows["a"]["state"] == "degraded"
    assert rows["a"]["decided_by"] == "dependency"


def test_05_required_stale_input_makes_the_output_stale():
    doc = two_artifact_estate()
    rows = resolve(doc, {"a": obs(), "b": obs(asof=OLD)})
    assert rows["a"]["state"] == "stale"
    assert rows["a"]["decided_by"] == "dependency"


def test_06_required_missing_input_makes_the_output_unavailable():
    doc = two_artifact_estate()
    rows = resolve(doc, {"a": obs(), "b": obs(exists=False, asof=None)})
    assert rows["a"]["state"] == "unavailable"
    assert rows["a"]["decided_by"] == "dependency"


def test_07_stale_output_beats_healthy_inputs():
    doc = two_artifact_estate()
    rows = resolve(doc, {"a": obs(asof=OLD), "b": obs()})
    assert rows["a"]["state"] == "stale"
    assert rows["a"]["decided_by"] == "content_watermark"
    assert rows["a"]["age_hours"] == pytest.approx(318.0)


def test_08_missing_output_beats_healthy_inputs():
    doc = two_artifact_estate()
    rows = resolve(doc, {"a": obs(exists=False, asof=None), "b": obs()})
    assert rows["a"]["state"] == "unavailable"
    assert rows["a"]["decided_by"] == "audit"
    # A definitively absent output has no watermark to fail to read: absence must not be
    # laundered into "could not look".
    assert rows["a"]["assessment_status"] == "complete"


# ---------------------------------------------------------------------------
# 9-11 — the reader plane and the time-basis law
# ---------------------------------------------------------------------------

def test_09_reader_stale_overrides_a_fresh_producer():
    doc = two_artifact_estate()
    rows = resolve(
        doc,
        {"a": obs(), "b": obs()},
        reader_observations={
            "a": {
                "source": "freshness_sentinel:prophet_us",
                "verdict": "stale",
                "clock_kind": "content",
                "observed_asof": OLD,
            }
        },
    )
    assert rows["a"]["state"] == "stale"
    assert rows["a"]["decided_by"] == "reader"
    assert "reader_stale_overrides_producer" in rows["a"]["reason_codes"]
    assert rows["a"]["reader_observation"]["verdict"] == "stale"


def test_09b_reader_content_fresh_governs_a_stale_producer_copy():
    """The other direction of the same law: the reader copy is what consumers receive."""
    doc = two_artifact_estate()
    rows = resolve(
        doc,
        {"a": obs(asof=OLD), "b": obs()},
        reader_observations={
            "a": {"source": "r2_audit:live_flow", "verdict": "fresh", "clock_kind": "content"}
        },
    )
    assert rows["a"]["state"] == "healthy"
    assert rows["a"]["decided_by"] == "reader"
    assert "producer_behind_reader" in rows["a"]["reason_codes"]


def test_10_content_watermark_outranks_a_fresh_transport_clock():
    doc = two_artifact_estate()
    rows = resolve(
        doc,
        {"a": obs(asof=OLD, mtime_utc=NOW, mtime_trusted=True), "b": obs()},
        reader_observations={
            "a": {"source": "r2_audit:stockdata", "verdict": "fresh", "clock_kind": "transport"}
        },
    )
    assert rows["a"]["state"] == "stale"
    assert rows["a"]["decided_by"] == "content_watermark"
    assert "transport_clock_outranked_by_content" in rows["a"]["reason_codes"]


def test_10b_stale_transport_never_overrides_a_fresh_content_watermark():
    doc = two_artifact_estate()
    rows = resolve(
        doc,
        {"a": obs(), "b": obs()},
        reader_observations={
            "a": {"source": "r2_audit:stockdata", "verdict": "stale", "clock_kind": "transport"}
        },
    )
    assert rows["a"]["state"] == "healthy"
    assert "transport_clock_outranked_by_content" in rows["a"]["reason_codes"]


def test_11_a_promised_asof_field_that_is_absent_is_blindness_not_a_fallback():
    doc = two_artifact_estate()
    rows = resolve(
        doc,
        {
            "a": obs(asof=None, asof_field_present=False, watermark_field_used="asof"),
            "b": obs(),
        },
    )
    assert rows["a"]["state"] is None
    assert rows["a"]["assessment_status"] == "could_not_look"
    assert "promised_asof_field_absent" in rows["a"]["reason_codes"]


def test_11b_an_observation_of_a_different_field_is_refused():
    doc = two_artifact_estate()
    rows = resolve(
        doc,
        {"a": obs(asof=FRESH, watermark_field_used="generated_utc"), "b": obs()},
        )
    assert rows["a"]["state"] is None
    assert rows["a"]["assessment_status"] == "could_not_look"
    assert "watermark_field_mismatch" in rows["a"]["reason_codes"]
    assert rows["a"]["source_asof"] is None


# ---------------------------------------------------------------------------
# 12-13 — blindness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "observation",
    [
        obs(exists=None, asof=None, presence_source=None),
        obs(parse_error="content does not parse (JSONDecodeError)"),
    ],
    ids=["unreachable", "unparseable"],
)
def test_12_an_unreadable_artifact_is_never_unavailable_or_healthy(observation):
    doc = two_artifact_estate()
    rows = resolve(doc, {"a": observation, "b": obs()})
    assert rows["a"]["state"] is None
    assert rows["a"]["assessment_status"] == "could_not_look"
    assert rows["a"]["display_confidence_state"] == "unknown"


def test_13_sparse_omission_is_blindness_not_absence():
    doc = two_artifact_estate()
    rows = resolve(
        doc,
        {"a": obs(exists=None, asof=None, presence_source=None, sparse_unmaterialized=True),
         "b": obs()},
    )
    assert rows["a"]["state"] is None
    assert "sparse_unmaterialized" in rows["a"]["reason_codes"]


def test_13b_tracked_but_unmaterialized_reads_from_head_as_a_real_observation(tmp_path):
    """The sparse-worktree half: a file only in HEAD still yields a REAL state."""
    root = _git_fixture_root(tmp_path)
    (root / "data" / "a.json").unlink()          # the sparse-cone omission
    view = CLI.build(root, now=NOW)
    row = {r["artifact_id"]: r for r in view["outputs"]}["a"]
    assert row["state"] == "healthy"
    assert row["assessment_status"] == "complete"
    assert "sparse_unmaterialized" not in row["reason_codes"]


# ---------------------------------------------------------------------------
# 14-17 — semantic health, provider noise, bounds, optional-upstream legality
# ---------------------------------------------------------------------------

def test_14_self_reported_partial_completeness_degrades_the_output():
    doc = two_artifact_estate()
    rows = resolve(
        doc,
        {"a": obs(), "b": obs()},
        self_health={
            "a": {"source": "foresight_health", "status": "degraded", "detail": "t1_fred DARK"}
        },
    )
    assert rows["a"]["state"] == "degraded"
    assert rows["a"]["decided_by"] == "self_health"
    assert rows["a"]["self_health"]["detail"] == "t1_fred DARK"


def test_15_a_failed_provider_rung_with_a_successful_output_stays_healthy():
    doc = two_artifact_estate()
    rows = resolve(
        doc,
        {"a": obs(), "b": obs()},
        provider_events={
            "a": [{"rung": "codex", "error_class": "usage_limit", "ok": False}]
        },
    )
    assert rows["a"]["state"] == "healthy"
    assert "provider_rung_failures_noted" in rows["a"]["reason_codes"]
    assert any(e["plane"] == "provider" for e in rows["a"]["evidence"])


def test_16_dependency_bound_is_exact_only_for_single_output_producers():
    doc = synapse_doc(
        a=artifact("data/a.json", producer=PRODUCER_A),
        a2=artifact("data/a2.json", producer=PRODUCER_A),
        b=artifact("data/b.json", producer=PRODUCER_B),
    )
    rows = resolve(doc, {aid: obs() for aid in doc["artifacts"]})
    assert rows["a"]["dependency_bound"] == "upper"
    assert rows["a2"]["dependency_bound"] == "upper"
    assert rows["b"]["dependency_bound"] == "exact"


def test_17_illegal_optional_upstreams_are_refused_by_validator_and_resolver():
    # (a) dangling id, (b) real artifact that is not an inferred upstream, (c) no notes.
    doc = two_artifact_estate(health_optional_upstreams=["ghost"], notes="declared")
    violations = validate_registry(doc, root=REPO)
    assert any("not a registered artifact id" in v for v in violations)
    rows = resolve(doc, {"a": obs(), "b": obs()})
    assert "illegal_optional_upstream:ghost" in rows["a"]["reason_codes"]
    assert rows["a"]["state"] is None
    assert rows["a"]["assessment_status"] == "partial"

    unrelated = synapse_doc(
        a=artifact("data/a.json", producer=PRODUCER_A,
                   health_optional_upstreams=["c"], notes="declared"),
        b=artifact("data/b.json", producer=PRODUCER_B, consumers=(PRODUCER_A,)),
        c=artifact("data/c.json", producer="engine/c.py"),
    )
    assert any(
        "not in the inferred direct-upstream set" in v
        for v in validate_registry(unrelated, root=REPO)
    )

    no_notes = two_artifact_estate(health_optional_upstreams=["b"])
    assert any("requires a notes field" in v for v in validate_registry(no_notes, root=REPO))

    legal = two_artifact_estate(health_optional_upstreams=["b"], notes="evidence here")
    assert not [
        v for v in validate_registry(legal, root=REPO) if "health_optional_upstreams" in v
    ]


def test_17b_the_live_registry_declares_zero_optional_upstreams():
    """The MECHANISM ships with no live entries: optionality needs producer evidence and
    none is adjudicated in this wave. Structural (a count of zero), not a content claim."""
    text = (REPO / "config" / "synapse.yml").read_text(encoding="utf-8")
    assert "health_optional_upstreams" not in text


# ---------------------------------------------------------------------------
# 18-20 — MUTATION TARGETS
# ---------------------------------------------------------------------------

def test_mutation_18_required_input_precedence():
    """MUTATION TARGET: reorder or drop precedence rules 2 and 4 (required inputs).

    Rule 2 (input unavailable -> unavailable) and rule 4 (input stale -> stale) must both
    fire while the output's own axes are clean.
    """
    doc = two_artifact_estate()
    missing = resolve(doc, {"a": obs(), "b": obs(exists=False, asof=None)})
    assert (missing["a"]["state"], missing["a"]["decided_by"]) == ("unavailable", "dependency")
    stale = resolve(doc, {"a": obs(), "b": obs(asof=OLD)})
    assert (stale["a"]["state"], stale["a"]["decided_by"]) == ("stale", "dependency")


def test_mutation_19_mtime_never_outranks_a_content_watermark():
    """MUTATION TARGET: let mtime decide freshness when a content watermark is present."""
    doc = two_artifact_estate()
    rows = resolve(doc, {"a": obs(asof=OLD, mtime_utc=NOW, mtime_trusted=True), "b": obs()})
    assert rows["a"]["state"] == "stale"
    assert rows["a"]["decided_by"] == "content_watermark"
    assert rows["a"]["age_hours"] == pytest.approx(318.0)


def test_mutation_20_could_not_look_is_never_converted():
    """MUTATION TARGET: convert the blindness short-circuit into healthy or unavailable."""
    doc = two_artifact_estate()
    for observation in (
        obs(exists=None, asof=None, presence_source=None),
        obs(asof="not-a-timestamp"),
        obs(asof=None, asof_field_present=False),
    ):
        rows = resolve(doc, {"a": observation, "b": obs()})
        assert rows["a"]["state"] is None, observation
        assert rows["a"]["assessment_status"] == "could_not_look"
        assert rows["a"]["state"] not in ("healthy", "unavailable")


# ---------------------------------------------------------------------------
# 21-22 — determinism and the import surface
# ---------------------------------------------------------------------------

def _git_fixture_root(tmp_path: Path, *, empty_artifact: bool = False) -> Path:
    """A committed one-engine estate: enough for the CLI's ladder to be real.

    *empty_artifact* commits a THIRD, zero-byte artifact. An empty blob is the one shape
    where the read ladder's two halves disagree — a 0-byte worktree file reads as ``""``,
    a 0-byte blob at HEAD reads as ABSENT — so it is the case any batched substitute is
    most likely to get subtly wrong (and did, on two live artifacts, before the fix).
    """
    root = tmp_path / "estate"
    (root / "config").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "engine").mkdir()
    entries = {
        "a": artifact("data/a.json", producer=PRODUCER_A),
        "b": artifact("data/b.json", producer=PRODUCER_B, consumers=(PRODUCER_A,)),
    }
    if empty_artifact:
        entries["empty"] = artifact("data/empty.json", producer="engine/empty.py")
        (root / "data" / "empty.json").write_text("", encoding="utf-8")
        (root / "engine" / "empty.py").write_text("", encoding="utf-8")
    doc = synapse_doc(**entries)
    (root / "config" / "synapse.yml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    (root / "data" / "a.json").write_text(json.dumps({"asof": FRESH}), encoding="utf-8")
    (root / "data" / "b.json").write_text(json.dumps({"asof": FRESH}), encoding="utf-8")
    (root / "engine" / "a.py").write_text("", encoding="utf-8")
    (root / "engine" / "b.py").write_text("", encoding="utf-8")
    env = {
        "GIT_AUTHOR_NAME": "t4", "GIT_AUTHOR_EMAIL": "t4@example.com",
        "GIT_COMMITTER_NAME": "t4", "GIT_COMMITTER_EMAIL": "t4@example.com",
        "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path),
    }
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True, env=env)
    return root


def test_21_the_cli_is_byte_identical_over_a_frozen_root(tmp_path, capsys):
    root = _git_fixture_root(tmp_path)
    argv = ["--root", str(root), "--now", NOW.isoformat()]
    assert CLI.main(argv) == 0
    first = capsys.readouterr().out
    assert CLI.main(argv) == 0
    second = capsys.readouterr().out
    assert first == second
    payload = json.loads(first)
    assert payload["schema"] == "mastermind.output_health.v1"
    assert payload["generated"]["observed_at"] == NOW.isoformat()
    assert {r["artifact_id"] for r in payload["outputs"]} == {"a", "b"}


def test_21b_the_cli_writes_nothing(tmp_path, capsys):
    root = _git_fixture_root(tmp_path)
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert CLI.main(["--root", str(root), "--now", NOW.isoformat(), "--summary"]) == 0
    after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert before == after
    assert "output health" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Batched git reads — a cost optimization that must be verdict-neutral
# ---------------------------------------------------------------------------

def test_batched_head_reads_are_verdict_identical_to_the_per_path_ladder(tmp_path):
    """Two batched ``git`` calls replaced ~2 process spawns per unmaterialized artifact
    (measured: 692s -> minutes on this repo's sparse worktree). The ONLY thing that makes
    that a legal trade is that it cannot move an answer, so the two paths are compared
    directly on a root where every artifact is read out of HEAD.

    A perf change that quietly reclassified one artifact would otherwise look exactly like
    a perf change that worked.
    """
    root = _git_fixture_root(tmp_path, empty_artifact=True)
    for name in ("a.json", "b.json", "empty.json"):
        (root / "data" / name).unlink()          # force the whole estate through HEAD

    fast = CLI.build(root, now=NOW)

    # Same build with BOTH batched paths disabled: presence falls back to the per-path
    # `git cat-file -t` probe, content to the per-path `git show`.
    real_head_blobs, real_prewarm = CLI._head_blobs, CLI._prewarm_head_contents
    try:
        CLI._head_blobs = lambda _root: None
        CLI._prewarm_head_contents = lambda _root, _rels: 0
        slow = CLI.build(root, now=NOW)
    finally:
        CLI._head_blobs, CLI._prewarm_head_contents = real_head_blobs, real_prewarm

    assert json.dumps(fast, sort_keys=True) == json.dumps(slow, sort_keys=True)
    # And the run being compared must actually have gone through HEAD — if both paths
    # read the worktree, the comparison proves nothing.
    assert fast["generated"]["root_mode"] == "git_head"
    states = {r["artifact_id"]: r["state"] for r in fast["outputs"]}
    assert states["a"] == "healthy" and states["b"] == "healthy"
    # The empty blob must reach the SAME reason code either way — the divergence that
    # made this test necessary was visible only here, never in a state.
    reasons = {r["artifact_id"]: r["reason_codes"] for r in fast["outputs"]}
    assert "watermark_unread" in reasons["empty"], reasons["empty"]


def test_the_prewarm_declines_rather_than_guesses(tmp_path):
    """Every path the batch does not warm must fall through, never resolve to a wrong or
    empty body. An unresolvable ref caches the ladder's own ``absent``; a blob over the
    cap is left entirely alone so the size-capped read still reports the cap."""
    root = _git_fixture_root(tmp_path)
    CLI.reset_caches()
    warmed = CLI._prewarm_head_contents(root, ["data/a.json", "data/nope.json", ""])
    assert warmed == 2
    assert CLI._READ_CACHE[(str(root), "data/a.json")][1] == "git"
    assert CLI._READ_CACHE[(str(root), "data/nope.json")] == (None, "absent")

    CLI.reset_caches()
    real_cap = CLI.PREWARM_SIZE_CAP
    try:
        CLI.PREWARM_SIZE_CAP = 1                 # every blob is now "too big"
        assert CLI._prewarm_head_contents(root, ["data/a.json"]) == 0
    finally:
        CLI.PREWARM_SIZE_CAP = real_cap
    assert (str(root), "data/a.json") not in CLI._READ_CACHE


def test_watermark_source_path_is_the_single_definition(tmp_path):
    """The prewarm and the reader must agree on WHICH file holds the watermark; a second
    copy of that rule would drift into warming the wrong bytes under the right key."""
    assert CLI.watermark_source_path({"path": "data/a.json", "format": "json"}) == "data/a.json"
    assert CLI.watermark_source_path({"path": "data/a.jsonl", "format": "jsonl"}) == "data/a.jsonl"
    assert CLI.watermark_source_path({"path": "data/a.parquet", "format": "parquet"}) == (
        "data/a.parquet.envelope.json"
    )
    assert CLI.watermark_source_path({"path": "data/a.csv", "format": "csv"}) is None
    assert CLI.watermark_source_path({"path": "", "format": "json"}) is None


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_22_the_resolver_imports_no_ranking_gating_or_sizing_module():
    """The cheap structural form of "no health field becomes a model input".

    The resolver may reach stdlib, ``typing`` and the temporal model and NOTHING else — so
    it cannot read a score, a rank, a size or a gate even by accident, and the review
    question stops being "does it use one" and becomes "is the import list still this".
    """
    allowed = {"__future__", "re", "datetime", "typing", "lib.dataos.temporal"}
    assert _imported_modules(REPO / "engine" / "output_health.py") == allowed

    cli_allowed = {
        "__future__", "argparse", "json", "subprocess", "sys", "datetime", "pathlib",
        "typing", "yaml", "engine.output_health", "scripts.build_intelligence_registry",
        "scripts.freshness_sentinel",
    }
    assert _imported_modules(REPO / "scripts" / "build_output_health.py") <= cli_allowed


# ---------------------------------------------------------------------------
# Property tests the commission adds beyond the numbered 22
# ---------------------------------------------------------------------------

def test_the_precedence_ladder_resolves_worst_first():
    """Each rule must win over every rule below it, pairwise, on one estate."""
    doc = two_artifact_estate(
        health_optional_upstreams=["b"], notes="optional by fixture declaration"
    )
    # b is optional here, so a's own axes and b's state are the only movers.
    ladder = [
        # (a observation, b observation, self_health for a, expected)
        (obs(exists=False, asof=None), obs(asof=OLD), "degraded", "unavailable"),
        (obs(asof=OLD), obs(asof=OLD), "degraded", "stale"),
        (obs(), obs(asof=OLD), "degraded", "degraded"),
        (obs(), obs(asof=OLD), None, "degraded"),
        (obs(), obs(), None, "healthy"),
    ]
    for a_obs, b_obs, semantic, expected in ladder:
        kwargs = {}
        if semantic:
            kwargs["self_health"] = {"a": {"source": "fixture", "status": semantic}}
        rows = resolve(doc, {"a": a_obs, "b": b_obs}, **kwargs)
        assert rows["a"]["state"] == expected, (a_obs["exists"], a_obs["content_asof_raw"], semantic)


def test_required_inputs_outrank_optional_ones():
    doc = synapse_doc(
        a=artifact("data/a.json", producer=PRODUCER_A,
                   health_optional_upstreams=["b"], notes="b optional"),
        b=artifact("data/b.json", producer=PRODUCER_B, consumers=(PRODUCER_A,)),
        c=artifact("data/c.json", producer="engine/c.py", consumers=(PRODUCER_A,)),
    )
    rows = resolve(doc, {"a": obs(), "b": obs(asof=OLD), "c": obs(exists=False, asof=None)})
    assert rows["a"]["state"] == "unavailable"
    assert rows["a"]["decided_by"] == "dependency"


def test_a_date_only_watermark_inside_sla_is_read_conservatively():
    doc = synapse_doc(a=artifact("data/a.json", producer=PRODUCER_A, sla=48))
    rows = resolve(doc, {"a": obs(asof="2026-08-14")})
    assert rows["a"]["state"] == "healthy"
    assert "date_only_conservative" in rows["a"]["reason_codes"]
    # end of 2026-08-14 is 12h AFTER `now`, so the conservative minimum age is negative.
    assert rows["a"]["age_hours"] == pytest.approx(-12.0)


def test_a_date_only_watermark_beyond_sla_cannot_separate_a_weekend_from_an_outage():
    doc = synapse_doc(a=artifact("data/a.json", producer=PRODUCER_A, sla=24))
    rows = resolve(doc, {"a": obs(asof="2026-08-10")})
    assert rows["a"]["state"] is None
    assert rows["a"]["assessment_status"] == "could_not_look"
    assert "date_only_calendar_unknown" in rows["a"]["reason_codes"]


def test_no_calendar_inference_appears_anywhere_in_the_resolver():
    """A weekend rule would have to name a weekday, a market or a calendar to exist."""
    source = (REPO / "engine" / "output_health.py").read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1].lower()   # skip the module docstring
    for needle in ("weekday", "isoweekday", "saturday", "sunday", "nyse", "calendar("):
        assert needle not in body, needle


def test_staleness_from_overrides_the_asof_field():
    doc = synapse_doc(
        a=artifact(
            "data/a.json", producer=PRODUCER_A, asof_field="asof",
            staleness_from="produced_at", sla=24,
        )
    )
    # An observation that read `asof` is REFUSED once the override names another field.
    refused = resolve(doc, {"a": obs(asof=FRESH, watermark_field_used="asof")})
    assert "watermark_field_mismatch" in refused["a"]["reason_codes"]
    honored = resolve(doc, {"a": obs(asof=FRESH, watermark_field_used="produced_at")})
    assert honored["a"]["state"] == "healthy"


def test_a_naive_watermark_is_coerced_but_disclosed():
    doc = synapse_doc(a=artifact("data/a.json", producer=PRODUCER_A))
    rows = resolve(doc, {"a": obs(asof="2026-08-14T06:00:00")})
    assert rows["a"]["state"] == "healthy"
    assert "naive_watermark_coerced_utc" in rows["a"]["reason_codes"]


def test_a_self_loop_is_excluded_from_the_inputs_it_would_gate():
    doc = synapse_doc(
        a=artifact("data/a.json", producer=PRODUCER_A, consumers=(PRODUCER_A,))
    )
    rows = resolve(doc, {"a": obs()})
    assert rows["a"]["required_inputs"] == []
    assert "self_input_excluded" in rows["a"]["reason_codes"]
    assert rows["a"]["state"] == "healthy"


def test_a_dependency_cycle_is_reported_not_recursed():
    doc = synapse_doc(
        a=artifact("data/a.json", producer=PRODUCER_A, consumers=(PRODUCER_B,)),
        b=artifact("data/b.json", producer=PRODUCER_B, consumers=(PRODUCER_A,)),
    )
    rows = resolve(doc, {"a": obs(), "b": obs()})
    cycled = [r for r in rows.values() if "dependency_cycle" in r["reason_codes"]]
    assert cycled, "the cycle must be disclosed on at least one member"
    assert all(r["state"] != "healthy" or r["assessment_status"] != "complete" for r in cycled)


def test_an_artifact_in_no_engine_cell_still_gets_a_record():
    doc = two_artifact_estate()
    registry = registry_for(doc, excluded_cells=(f"{PRODUCER_B}::test-program",))
    rows = resolve(doc, {"a": obs(), "b": obs()}, registry=registry)
    assert rows["b"]["engine_id"] is None
    assert "not_in_engine_registry" in rows["b"]["reason_codes"]
    assert rows["b"]["state"] == "healthy"          # health is still computed
    assert rows["b"]["authority"] == "display"      # homogeneous cell answers exactly


def test_output_class_comes_from_the_t1_overlay_and_is_never_guessed():
    doc = two_artifact_estate()
    rows = resolve(doc, {"a": obs(), "b": obs()}, registry=registry_for(doc))
    assert rows["a"]["output_class"] is None
    curated = resolve(
        doc, {"a": obs(), "b": obs()}, registry=registry_for(doc, output_class="ranking")
    )
    assert curated["a"]["output_class"] == "ranking"


def test_display_confidence_tracks_state():
    doc = two_artifact_estate()
    cases = {
        "healthy": (obs(), "full"),
        "stale": (obs(asof=OLD), "none"),
        "unavailable": (obs(exists=False, asof=None), "none"),
        "blind": (obs(exists=None, asof=None, presence_source=None), "unknown"),
    }
    for label, (observation, expected) in cases.items():
        rows = resolve(doc, {"a": observation, "b": obs()})
        assert rows["a"]["display_confidence_state"] == expected, label
    degraded = resolve(
        doc, {"a": obs(), "b": obs()},
        self_health={"a": {"source": "fixture", "status": "degraded"}},
    )
    assert degraded["a"]["display_confidence_state"] == "reduced"


def test_a_naive_now_is_refused():
    doc = two_artifact_estate()
    with pytest.raises(TemporalError):
        OH.resolve_output_health(
            synapse=doc,
            registry=registry_for(doc),
            observations={},
            now=datetime(2026, 8, 14, 12, 0, 0),
        )


def test_the_summary_counts_equal_the_records():
    doc = synapse_doc(
        a=artifact("data/a.json", producer=PRODUCER_A),
        b=artifact("data/b.json", producer=PRODUCER_B, consumers=(PRODUCER_A,)),
        c=artifact("data/c.json", producer="engine/c.py", storage="r2"),
    )
    view = OH.resolve_output_health(
        synapse=doc,
        registry=registry_for(doc),
        observations={"a": obs(), "b": obs(asof=OLD), "c": obs(exists=None, asof=None)},
        now=NOW,
    )
    summary = view["summary"]
    assert summary["n_outputs"] == len(view["outputs"]) == 3
    for key, field in (
        ("by_state", "state"),
        ("by_assessment_status", "assessment_status"),
        ("by_dependency_bound", "dependency_bound"),
        ("by_decided_by", "decided_by"),
    ):
        rebuilt: dict[str, int] = {}
        for row in view["outputs"]:
            label = "null" if row[field] is None else str(row[field])
            rebuilt[label] = rebuilt.get(label, 0) + 1
        assert summary[key] == dict(sorted(rebuilt.items())), key
    assert sum(summary["by_state"].values()) == 3


def test_every_reason_code_stays_inside_the_closed_vocabulary():
    doc = synapse_doc(
        a=artifact("data/a.json", producer=PRODUCER_A, health_optional_upstreams=["ghost"],
                   notes="declared", storage="gitignored-local"),
        b=artifact("data/b.json", producer=PRODUCER_B, consumers=(PRODUCER_A,),
                   asof_field=None, sla=None),
        c=artifact("data/<SYM>.json", producer="engine/c.py", storage="r2"),
    )
    view = OH.resolve_output_health(
        synapse=doc,
        registry=registry_for(doc),
        observations={
            "a": obs(exists=None, asof=None, presence_source=None),
            "b": obs(asof=None),
            "c": obs(exists=None, asof=None, presence_source=None),
        },
        reader_observations={"b": {"source": "s", "verdict": "indeterminate",
                                   "clock_kind": "transport"}},
        self_health={"b": {"source": "fixture", "status": "unknown"}},
        provider_events={"b": [{"rung": "codex", "error_class": "timeout"}]},
        now=NOW,
    )
    seen = {OH.reason_base(code) for row in view["outputs"] for code in row["reason_codes"]}
    assert seen, "the fixture must exercise some reasons"
    assert seen <= OH.REASON_CODES, sorted(seen - OH.REASON_CODES)
    rows = {r["artifact_id"]: r for r in view["outputs"]}
    assert "placeholder_path" in rows["c"]["reason_codes"]
    assert "runtime_only_unobservable" in rows["a"]["reason_codes"]
    assert "no_freshness_contract" in rows["b"]["reason_codes"]
    assert rows["b"]["state"] is None and rows["b"]["assessment_status"] == "partial"


def test_an_artifact_with_no_freshness_contract_can_still_be_healthy():
    doc = synapse_doc(a=artifact("data/a.json", producer=PRODUCER_A, asof_field=None, sla=None))
    rows = resolve(doc, {"a": obs(asof=None)})
    assert rows["a"]["state"] == "healthy"
    assert rows["a"]["decided_by"] == "audit"
    assert "no_freshness_contract" in rows["a"]["reason_codes"]


def test_a_declared_watermark_with_no_sla_leaves_freshness_vacuous_but_disclosed():
    doc = synapse_doc(a=artifact("data/a.json", producer=PRODUCER_A, sla=None))
    rows = resolve(doc, {"a": obs(asof=OLD)})
    assert rows["a"]["state"] == "healthy"
    assert "no_sla_declared" in rows["a"]["reason_codes"]
    assert rows["a"]["age_hours"] == pytest.approx(318.0)


def test_untrusted_mtime_blocks_healthy_without_inventing_staleness():
    doc = synapse_doc(a=artifact("data/a.json", producer=PRODUCER_A, asof_field=None, sla=24))
    rows = resolve(doc, {"a": obs(asof=None, mtime_utc=NOW - timedelta(hours=100))})
    assert rows["a"]["state"] is None
    assert rows["a"]["assessment_status"] == "partial"
    assert "write_time_untrusted" in rows["a"]["reason_codes"]
    trusted = resolve(
        doc, {"a": obs(asof=None, mtime_utc=NOW - timedelta(hours=100), mtime_trusted=True)}
    )
    assert trusted["a"]["state"] == "stale"
    assert trusted["a"]["decided_by"] == "write_time"


def test_a_reader_that_could_not_answer_blocks_nothing():
    doc = two_artifact_estate()
    rows = resolve(
        doc, {"a": obs(), "b": obs()},
        reader_observations={
            "a": {"source": "sentinel", "verdict": "indeterminate", "clock_kind": "content"}
        },
    )
    assert rows["a"]["state"] == "healthy"
    assert rows["a"]["assessment_status"] == "complete"
    assert "reader_indeterminate" in rows["a"]["reason_codes"]


def test_two_readers_of_one_artifact_are_ranked_by_clock_then_severity():
    """An artifact can carry both a sentinel surface and an R2 anchor. The stronger clock
    governs, and between equals the WORSE observation does — never the alphabet."""
    doc = two_artifact_estate()
    rows = resolve(
        doc,
        {"a": obs(), "b": obs()},
        reader_observations={
            "a": [
                {"source": "z_sentinel", "verdict": "stale", "clock_kind": "content"},
                {"source": "a_audit", "verdict": "fresh", "clock_kind": "content"},
            ]
        },
    )
    assert rows["a"]["state"] == "stale"
    assert rows["a"]["reader_observation"]["source"] == "z_sentinel"

    # A content-clock reader outranks a transport-clock one even when the transport row
    # sorts first by name and carries the worse verdict.
    ranked = resolve(
        doc,
        {"a": obs(), "b": obs()},
        reader_observations={
            "a": [
                {"source": "a_audit", "verdict": "stale", "clock_kind": "transport"},
                {"source": "z_sentinel", "verdict": "fresh", "clock_kind": "content"},
            ]
        },
    )
    assert ranked["a"]["reader_observation"]["source"] == "z_sentinel"
    assert ranked["a"]["state"] == "healthy"


def test_a_monitor_may_not_grade_its_own_producers_output():
    doc = synapse_doc(
        health=artifact("data/health.json", producer="engine/monitor.py"),
        mirror=artifact("site/health.json", producer="engine/monitor.py"),
        other=artifact("data/other.json", producer=PRODUCER_B),
    )
    evidence = {"source": "neuralweb_health", "status": "degraded", "source_artifact": "health"}
    rows = resolve(
        doc,
        {aid: obs() for aid in doc["artifacts"]},
        self_health={aid: dict(evidence) for aid in doc["artifacts"]},
    )
    for aid in ("health", "mirror"):
        assert rows[aid]["self_health"] is None
        assert "self_monitor_no_self_evidence" in rows[aid]["reason_codes"]
        assert rows[aid]["state"] == "healthy"
    assert rows["other"]["state"] == "degraded"


def test_the_view_schema_is_not_a_registered_synapse_artifact():
    """No fixed point: T4 commits nothing, so nothing here can grade itself."""
    text = (REPO / "config" / "synapse.yml").read_text(encoding="utf-8")
    assert OH.SCHEMA not in text
    assert "output_health" not in text


def test_the_resolver_is_pure_over_repeated_calls():
    doc = two_artifact_estate()
    observations = {"a": obs(), "b": obs(asof=OLD)}
    first = OH.resolve_output_health(
        synapse=doc, registry=registry_for(doc), observations=observations, now=NOW
    )
    second = OH.resolve_output_health(
        synapse=doc, registry=registry_for(doc), observations=observations, now=NOW
    )
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert observations["a"]["exists"] is True      # inputs untouched


def test_every_state_bearing_record_names_the_plane_that_decided_it():
    doc = two_artifact_estate()
    for observation in (obs(), obs(asof=OLD), obs(exists=False, asof=None),
                        obs(exists=None, asof=None, presence_source=None)):
        rows = resolve(doc, {"a": observation, "b": obs()})
        row = rows["a"]
        if row["state"] is None:
            assert row["decided_by"] is None
        else:
            assert row["decided_by"] in OH.DECIDED_BY_VALUES, row
