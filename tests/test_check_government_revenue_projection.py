"""Publication-fence tests for the Government Revenue public projection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_government_revenue, build_government_revenue_candidates
from scripts.check_government_revenue_projection import (
    ProjectionDriftError,
    _assert_workspace_admits_its_award_events,
    validate_projection,
)
from engine.government_revenue.workspace import build_procurement_workspace
from engine.government_revenue.dossiers import build_dossier_payload
from engine.government_revenue.subaward_dossiers import build_subaward_dossier_payload
from engine.government_revenue.entity_resolution import (
    build_recipient_resolution_coverage,
    load_recipient_entity_graph,
)
from tests.test_government_revenue_workspace import reviewed_award_event


ROOT = Path(__file__).resolve().parents[1]
RENDER_LANES = (
    ROOT / ".github" / "workflows" / "render.yml",
    ROOT / ".github" / "workflows" / "engine-render.yml",
)


def _porcelain_rebase_at(lane: Path, source: str) -> int:
    """Keep the render lane's explicit fetched-main rebase fail-closed."""
    if lane.name == "render.yml":
        rebase = source.index("git rebase --autostash -X theirs origin/main")
        assert source.index("push_fetch_main_for_rebase") < rebase
        return rebase
    return source.index("git pull --rebase --autostash -X theirs origin main")


def _generation(
    root: Path,
    *,
    recipient_activation: bool = False,
    award_events: list[dict] | None = None,
) -> tuple[Path, Path, Path]:
    template_dir = root / "templates"
    template_dir.mkdir(parents=True)
    template_dir.joinpath("government_revenue.html.j2").write_text(
        """<button data-mode="candidates">Candidate Radar</button><button data-mode="companies">Companies</button>
<main id="gov-workspace"><div id="queueList"></div><aside id="inspectorPane"></aside></main>
<aside id="evidenceDrawer"></aside>
<script id="gov-data" type="application/json">{{ payload_json|safe }}</script>
<script src="government-revenue-candidate-radar.js"></script>
""",
        encoding="utf-8",
    )
    workspace = build_procurement_workspace(
        {
            "events": [],
            "opportunities": [],
            "freshness": {"status": "unavailable"},
            "market": {"active_opportunities": 0},
        },
        [{
            "ticker": "TEST",
            "name": "Test Systems",
            "metrics": {"ttm_obligations": 100.0},
            "confidence": {"level": "medium"},
            "entity_match": {"method": "exact_uei"},
            "recompete_candidates": [{
                "award_id": "TEST-PIID",
                "generated_award_id": "CONT_AWD_TEST",
                "award_key": "CONT_AWD_TEST",
                "end_date": "2027-01-01",
                "days_to_end": 152,
                "total_obligated": 25.0,
                "known_at": "2026-08-02T00:00:00Z",
                "effective_at": "2026-08-01T00:00:00Z",
                "source_url": "https://www.usaspending.gov/award/CONT_AWD_TEST/",
            }],
        }],
        as_of="2026-08-02",
        known_at="2026-08-02T00:00:00Z",
        award_events=award_events,
        award_event_freshness=(
            {"status": "ok"} if award_events is not None else None
        ),
    )
    workspace["bundle_id"] = build_government_revenue._workspace_bundle_id(workspace)
    payload = {
        "schema_version": "company_government_revenue.v1",
        "as_of": "2026-08-02",
        "known_at": "2026-08-02T00:00:00Z",
        "procurement_workspace": workspace,
        "companies": [],
    }
    canonical_dir = root / "data" / "government_revenue"
    canonical_dir.mkdir(parents=True)
    if recipient_activation:
        graph = {
            "contract": "government_recipient_entity_graph.v1",
            "schema_version": "1.1.0",
            "graph_id": "recipient-graph:projection-empty",
            "graph_known_at": "2026-08-02T00:00:00Z",
            "graph_effective_at": "2026-08-02T00:00:00Z",
            "evidence": [],
            "companies": [],
            "legal_entities": [],
            "identifiers": [],
            "ownership_edges": [],
            "blocks": [],
            "conflicts": [],
            "overrides": [],
        }
        canonical_dir.joinpath("recipient_entity_graph.json").write_text(
            json.dumps(graph), encoding="utf-8"
        )
        coverage = build_recipient_resolution_coverage(
            [],
            [],
            load_recipient_entity_graph(graph, as_of=payload["as_of"]),
            as_of=payload["as_of"],
            snapshot_amount_field="total_obligation",
            action_amount_field="federal_action_obligation",
        )
        payload["freshness"] = {
            "award_events": {"recipient_resolution_coverage": coverage}
        }
        workspace["freshness"]["award_events"][
            "recipient_resolution_coverage"
        ] = coverage
        canonical_dir.joinpath("recipient_resolution_coverage.json").write_text(
            build_government_revenue._canonical_json(coverage), encoding="utf-8"
        )
        workspace["bundle_id"] = build_government_revenue._workspace_bundle_id(
            workspace
        )
    canonical_dir.joinpath("latest.json").write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )
    canonical_dir.joinpath("workspace.json").write_text(
        build_government_revenue._canonical_json(workspace), encoding="utf-8"
    )
    dossier = build_dossier_payload(root, as_of="2026-08-02")
    canonical_dir.joinpath("dossiers.json").write_text(
        build_government_revenue._canonical_json(dossier), encoding="utf-8"
    )
    subaward_dossier = build_subaward_dossier_payload(
        root,
        as_of="2026-08-02",
        prime_award_key_by_generated_id=(
            build_government_revenue._prime_award_key_by_generated_id(dossier)
        ),
    )
    canonical_dir.joinpath("subaward_dossiers.json").write_text(
        build_government_revenue._canonical_json(subaward_dossier), encoding="utf-8"
    )
    return build_government_revenue.build_site_only(root)


def test_projection_fence_accepts_one_canonical_compact_generation(tmp_path: Path) -> None:
    _generation(tmp_path)

    result = validate_projection(tmp_path)

    assert result["events"] == 1
    assert result["bundle_id"].startswith("grw2-")
    assert result["dossier_content_id"].startswith("grd1-")
    assert result["subaward_dossier_content_id"].startswith("grsd1-")
    assert result["subaward_dossiers"] == 0
    assert result["html_bytes"] < build_government_revenue.RAW_HTML_BUDGET_BYTES


def test_projection_fence_accepts_source_owned_candidate_ui_before_first_materialization(
    tmp_path: Path,
) -> None:
    _generation(tmp_path)
    html_path = tmp_path / "site" / "government_revenue.html"
    html = html_path.read_text(encoding="utf-8")
    for marker, replacement in {
        'data-mode="candidates"': 'data-mode="staged-candidates"',
        'data-mode="companies"': 'data-mode="staged-companies"',
        'src="government-revenue-candidate-radar.js"': 'src="candidate-radar-pending.js"',
    }.items():
        html = html.replace(marker, replacement)
    html_path.write_text(html, encoding="utf-8")

    result = validate_projection(tmp_path)

    assert result["candidate_content_id"] is None


@pytest.mark.parametrize(
    ("script_ref", "accepted"),
    (
        ("government-revenue-candidate-radar.js", True),
        ("government-revenue-candidate-radar.js?v=0123abcd", True),
        ("government-revenue-candidate-radar.js?v=custom", False),
        ("candidate-radar-pending.js", False),
    ),
)
def test_projection_fence_accepts_only_canonical_candidate_script_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script_ref: str,
    accepted: bool,
) -> None:
    _generation(tmp_path)
    html_path = tmp_path / "site" / "government_revenue.html"
    html = html_path.read_text(encoding="utf-8").replace(
        "government-revenue-candidate-radar.js", script_ref
    )
    html_path.write_text(html, encoding="utf-8")
    monkeypatch.setattr(
        build_government_revenue_candidates,
        "verify_candidate_artifacts",
        lambda *_args, **_kwargs: {"status": "verified"},
    )

    if accepted:
        validate_projection(tmp_path)
    else:
        with pytest.raises(
            ProjectionDriftError,
            match="public HTML is missing governed workspace markers",
        ):
            validate_projection(tmp_path)


def test_projection_fence_requires_candidate_markers_in_the_canonical_template(
    tmp_path: Path,
) -> None:
    _generation(tmp_path)
    template_path = tmp_path / "templates" / "government_revenue.html.j2"
    template = template_path.read_text(encoding="utf-8").replace(
        'data-mode="candidates"', 'data-mode="pending"'
    )
    template_path.write_text(template, encoding="utf-8")

    with pytest.raises(ProjectionDriftError, match="template is missing candidate markers"):
        validate_projection(tmp_path)


def test_projection_fence_rejects_stale_public_latest_twin(tmp_path: Path) -> None:
    _generation(tmp_path)
    public_latest = tmp_path / "site" / "government-revenue-data" / "latest.json"
    public_latest.write_text('{"stale":true}', encoding="utf-8")

    with pytest.raises(ProjectionDriftError, match="latest twin differs"):
        validate_projection(tmp_path)


def test_projection_fence_accepts_strict_recipient_graph_and_coverage_binding(
    tmp_path: Path,
) -> None:
    _generation(tmp_path, recipient_activation=True)

    result = validate_projection(tmp_path)

    assert result["recipient_graph_id"] == "recipient-graph:projection-empty"


@pytest.mark.parametrize(
    "target",
    ("recipient_entity_graph.json", "recipient_resolution_coverage.json"),
)
def test_projection_fence_rejects_missing_recipient_activation_member(
    tmp_path: Path,
    target: str,
) -> None:
    _generation(tmp_path, recipient_activation=True)
    (tmp_path / "data" / "government_revenue" / target).unlink()

    with pytest.raises(ProjectionDriftError, match="recipient"):
        validate_projection(tmp_path)


def test_projection_fence_rejects_invalid_graph_or_mismatched_coverage(
    tmp_path: Path,
) -> None:
    _generation(tmp_path, recipient_activation=True)
    graph_path = (
        tmp_path / "data" / "government_revenue" / "recipient_entity_graph.json"
    )
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["contract"] = "invalid.v0"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    with pytest.raises(ProjectionDriftError, match="recipient activation"):
        validate_projection(tmp_path)

    mismatch_root = tmp_path / "mismatch"
    _generation(mismatch_root, recipient_activation=True)
    coverage_path = (
        mismatch_root
        / "data"
        / "government_revenue"
        / "recipient_resolution_coverage.json"
    )
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    coverage["limitations"].append("tampered but schema-valid keyed representation")
    coverage_path.write_text(
        build_government_revenue._canonical_json(coverage), encoding="utf-8"
    )
    with pytest.raises(ProjectionDriftError, match="differs from embedded"):
        validate_projection(mismatch_root)


def test_projection_fence_rejects_stale_public_dossier_twin(tmp_path: Path) -> None:
    _generation(tmp_path)
    public_dossier = tmp_path / "site" / "government-revenue-data" / "dossiers.json"
    public_dossier.write_text('{"stale":true}', encoding="utf-8")

    with pytest.raises(ProjectionDriftError, match="dossier twin differs"):
        validate_projection(tmp_path)


def test_projection_fence_rejects_stale_public_subaward_dossier_twin(tmp_path: Path) -> None:
    _generation(tmp_path)
    public_dossier = (
        tmp_path / "site" / "government-revenue-data" / "subaward-dossiers.json"
    )
    public_dossier.write_text('{"stale":true}', encoding="utf-8")

    with pytest.raises(ProjectionDriftError, match="subaward dossier twin differs"):
        validate_projection(tmp_path)


@pytest.mark.parametrize(
    "canonical_name, public_name, label",
    (
        ("budget_program_graph.json", "budget-program.json", "DoD budget/program graph"),
        ("idv_dossiers.json", "idv-dossiers.json", "IDV dossier"),
    ),
)
def test_projection_fence_rejects_one_sided_optional_wave8_rail(
    tmp_path: Path,
    canonical_name: str,
    public_name: str,
    label: str,
) -> None:
    _generation(tmp_path)
    assert not (tmp_path / "site" / "government-revenue-data" / public_name).exists()
    path = tmp_path / "data" / "government_revenue" / canonical_name
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ProjectionDriftError, match=rf"{label} canonical/public pair is incomplete"):
        validate_projection(tmp_path)


def test_projection_fence_rejects_matching_twins_with_invalid_schema(
    tmp_path: Path,
) -> None:
    _generation(tmp_path)
    canonical_latest = tmp_path / "data" / "government_revenue" / "latest.json"
    public_latest = tmp_path / "site" / "government-revenue-data" / "latest.json"
    payload = json.loads(canonical_latest.read_text(encoding="utf-8"))
    payload["schema_version"] = "malformed.v0"
    raw = json.dumps(payload, separators=(",", ":"))
    canonical_latest.write_text(raw, encoding="utf-8")
    public_latest.write_text(raw, encoding="utf-8")

    with pytest.raises(ProjectionDriftError, match="canonical latest schema is invalid"):
        validate_projection(tmp_path)


def test_projection_fence_rejects_full_payload_or_missing_workspace_shell(
    tmp_path: Path,
) -> None:
    _generation(tmp_path)
    html = tmp_path / "site" / "government_revenue.html"
    html.write_text(
        "<main>legacy</main>"
        + ("x" * (build_government_revenue.RAW_HTML_BUDGET_BYTES + 1)),
        encoding="utf-8",
    )

    with pytest.raises(
        ProjectionDriftError,
        match=rf"exceeds {build_government_revenue.RAW_HTML_BUDGET_BYTES} bytes",
    ):
        validate_projection(tmp_path)

    html.write_text("<main>legacy</main>", encoding="utf-8")
    with pytest.raises(ProjectionDriftError, match="missing governed workspace markers"):
        validate_projection(tmp_path)


def test_projection_fence_rejects_shell_bundle_mismatch(tmp_path: Path) -> None:
    _generation(tmp_path)
    html_path = tmp_path / "site" / "government_revenue.html"
    html = html_path.read_text(encoding="utf-8")
    html_path.write_text(
        html.replace(
            '"bundle_id":"grw2-',
            '"bundle_id":"grw2-ffffffffffffffffffffffff',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProjectionDriftError, match="bundle_id differs"):
        validate_projection(tmp_path)


def test_projection_fence_rejects_stale_company_shell_with_current_bundle(
    tmp_path: Path,
) -> None:
    _generation(tmp_path)
    html_path = tmp_path / "site" / "government_revenue.html"
    html = html_path.read_text(encoding="utf-8")
    html_path.write_text(
        html.replace('"companies":[]', '"companies":[{"ticker":"STALE"}]', 1),
        encoding="utf-8",
    )

    with pytest.raises(ProjectionDriftError, match="differs semantically"):
        validate_projection(tmp_path)


@pytest.mark.parametrize("lane", RENDER_LANES, ids=lambda path: path.name)
def test_render_lanes_validate_projection_after_final_heals_and_before_commit(
    lane: Path,
) -> None:
    source = lane.read_text(encoding="utf-8")
    commit_step = source.index("- name: commit rendered site")
    block = source[commit_step:]
    staged_heal = block.index("push_staged_heal site/ templates/ || exit 1")
    projection_guard = block.index(
        "python -m scripts.check_government_revenue_projection", staged_heal
    )
    commit = min(
        position
        for needle in ('commit_index "$RENDER_MESSAGE"', 'git commit -m "engine-render:')
        if (position := block.find(needle, projection_guard)) != -1
    )

    assert staged_heal < projection_guard < commit


@pytest.mark.parametrize("lane", RENDER_LANES, ids=lambda path: path.name)
def test_render_lanes_refuse_to_push_an_uncommitted_projection(lane: Path) -> None:
    source = lane.read_text(encoding="utf-8")
    rebase = _porcelain_rebase_at(lane, source)
    post_rebase = source[rebase:]
    head_gate = post_rebase.index("git diff --quiet HEAD --")
    final_guard = post_rebase.index(
        "python -m scripts.check_government_revenue_projection", head_gate
    )
    push = post_rebase.index("if push_do", final_guard)

    assert head_gate < final_guard < push
    assert "site/government_revenue.html" in post_rebase[head_gate:final_guard]
    assert "site/government-revenue-data/latest.json" in post_rebase[head_gate:final_guard]
    assert "site/government-revenue-data/workspace.json" in post_rebase[head_gate:final_guard]
    assert "site/government-revenue-data/dossiers.json" in post_rebase[head_gate:final_guard]
    assert "site/government-revenue-data/idv-dossiers.json" in post_rebase[head_gate:final_guard]
    assert "site/government-revenue-data/budget-program.json" in post_rebase[head_gate:final_guard]


def test_render_metadata_replay_blocks_newer_procurement_truth_or_builder() -> None:
    source = (ROOT / ".github" / "workflows" / "render.yml").read_text(
        encoding="utf-8"
    )
    replay = source.index("PUBLISH_COMMIT=$(push_metadata_replay_commit")
    inputs = source.rfind("GOVREV_PROJECTION_INPUTS=(", 0, replay)
    gate = source.rfind('git diff --quiet "$RENDER_PARENT" origin/main --', 0, replay)
    condition = source[gate:replay]
    guarded_inputs = source[inputs:gate]

    assert "site/ templates/" in condition
    assert '"${GOVREV_PROJECTION_INPUTS[@]}"' in condition
    for path in (
        "data/government_revenue/",
        "lib/pages.py",
        "scripts/build_government_revenue.py",
        "scripts/build_government_revenue_candidates.py",
        "scripts/check_government_revenue_projection.py",
        "scripts/inject_data_base.py",
        "scripts/externalize_css.py",
        "scripts/optimize_assets.py",
        "scripts/check_template_site_sync.py",
    ):
        assert path in guarded_inputs


def _rewrite_canonical_workspace(root: Path, mutate) -> None:
    """Re-publish one generation after editing its canonical coverage block."""
    canonical_dir = root / "data" / "government_revenue"
    latest = json.loads((canonical_dir / "latest.json").read_text(encoding="utf-8"))
    workspace = latest["procurement_workspace"]
    mutate(workspace["coverage"])
    workspace["bundle_id"] = build_government_revenue._workspace_bundle_id(workspace)
    canonical_dir.joinpath("latest.json").write_text(
        json.dumps(latest, separators=(",", ":")), encoding="utf-8"
    )
    canonical_dir.joinpath("workspace.json").write_text(
        build_government_revenue._canonical_json(workspace), encoding="utf-8"
    )
    build_government_revenue.build_site_only(root)


def test_projection_fence_accepts_a_curator_shaped_reviewed_award_event(
    tmp_path: Path,
) -> None:
    """The published generation must carry the reviewed issuer impact, not drop it."""
    generation = _generation(tmp_path, award_events=[reviewed_award_event()])
    assert generation

    result = validate_projection(tmp_path)

    workspace = json.loads(
        (tmp_path / "data" / "government_revenue" / "workspace.json").read_text(
            encoding="utf-8"
        )
    )
    coverage = workspace["coverage"]
    assert coverage["award_events"]["rejected"] == 0
    assert coverage["award_events"]["first_rejection_reason"] is None
    assert coverage["by_mapping_class"]["reviewed"]["visible"] == 1
    assert coverage["by_mapping_class"]["reviewed"]["truncated_by_cap"] == 0
    assert result["events"] == 2


def test_projection_fence_refuses_a_generation_that_rejected_award_events(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A nonzero rejection count must fail CI, not sit unread in the artifact.

    The event is rejected by the real contract gate — its ownership path carries
    an uncontracted terminal relationship — rather than by a hand-set counter, so
    this pins the same path that silently dropped every reviewed issuer impact.
    """
    poisoned = reviewed_award_event()
    poisoned["listed_company_impacts"][0]["ownership_path"][-1]["relationship"] = (
        "not_a_contracted_relationship"
    )
    _generation(tmp_path, award_events=[poisoned])
    workspace = json.loads(
        (tmp_path / "data" / "government_revenue" / "workspace.json").read_text(
            encoding="utf-8"
        )
    )
    assert workspace["coverage"]["award_events"]["rejected"] == 1

    with pytest.raises(ProjectionDriftError) as excinfo:
        validate_projection(tmp_path)

    assert "rejected 1 award event(s)" in str(excinfo.value)
    assert "ownership_path.1.relationship" in str(excinfo.value)
    annotations = [
        line for line in capsys.readouterr().out.splitlines()
        if line.startswith("::")
    ]
    assert annotations, "the failure must be visible in the Actions summary"
    assert annotations[0].startswith("::error title=govrev-rejected-events::")


def test_projection_fence_refuses_a_generation_that_truncated_reviewed_events(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reviewed rows carry the issuer impacts; the display cap must never eat one."""
    _generation(tmp_path, award_events=[reviewed_award_event()])

    def _truncate_reviewed(coverage: dict) -> None:
        coverage["by_mapping_class"]["reviewed"]["available_before_cap"] = 4
        coverage["by_mapping_class"]["reviewed"]["truncated_by_cap"] = 3

    _rewrite_canonical_workspace(tmp_path, _truncate_reviewed)

    with pytest.raises(ProjectionDriftError) as excinfo:
        validate_projection(tmp_path)

    assert "dropped 3 reviewed event(s)" in str(excinfo.value)
    annotations = [
        line for line in capsys.readouterr().out.splitlines()
        if line.startswith("::")
    ]
    assert annotations
    assert annotations[0].startswith("::error title=govrev-truncated-reviewed-events::")


@pytest.mark.parametrize(
    "workspace",
    (
        {},
        {"coverage": {}},
        {"coverage": {"award_events": {}}},
        {"coverage": {"award_events": {"rejected": None}}},
        {"coverage": {"award_events": {"rejected": -1}}},
    ),
)
def test_award_event_admission_guard_reads_the_counter_or_fails_closed(
    workspace: dict,
) -> None:
    """A missing counter is an unmeasured generation, never an implicit zero.

    The v2 workspace contract makes ``rejected`` required, so a published
    generation cannot reach the fence without it — this pins the guard's own
    prologue rather than a path the schema already closes.
    """
    with pytest.raises(ProjectionDriftError):
        _assert_workspace_admits_its_award_events(workspace)
