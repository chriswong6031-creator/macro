"""Publication-fence tests for the Government Revenue public projection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_government_revenue
from scripts.check_government_revenue_projection import (
    ProjectionDriftError,
    validate_projection,
)
from engine.government_revenue.workspace import build_procurement_workspace
from engine.government_revenue.dossiers import build_dossier_payload


ROOT = Path(__file__).resolve().parents[1]
RENDER_LANES = (
    ROOT / ".github" / "workflows" / "render.yml",
    ROOT / ".github" / "workflows" / "engine-render.yml",
)


def _generation(root: Path) -> tuple[Path, Path, Path]:
    template_dir = root / "templates"
    template_dir.mkdir(parents=True)
    template_dir.joinpath("government_revenue.html.j2").write_text(
        """<main id="gov-workspace"><div id="queueList"></div><aside id="inspectorPane"></aside></main>
<aside id="evidenceDrawer"></aside>
<script id="gov-data" type="application/json">{{ payload_json|safe }}</script>
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
    return build_government_revenue.build_site_only(root)


def test_projection_fence_accepts_one_canonical_compact_generation(tmp_path: Path) -> None:
    _generation(tmp_path)

    result = validate_projection(tmp_path)

    assert result["events"] == 1
    assert result["bundle_id"].startswith("grw2-")
    assert result["dossier_content_id"].startswith("grd1-")
    assert result["html_bytes"] < 250_000


def test_projection_fence_rejects_stale_public_latest_twin(tmp_path: Path) -> None:
    _generation(tmp_path)
    public_latest = tmp_path / "site" / "government-revenue-data" / "latest.json"
    public_latest.write_text('{"stale":true}', encoding="utf-8")

    with pytest.raises(ProjectionDriftError, match="latest twin differs"):
        validate_projection(tmp_path)


def test_projection_fence_rejects_stale_public_dossier_twin(tmp_path: Path) -> None:
    _generation(tmp_path)
    public_dossier = tmp_path / "site" / "government-revenue-data" / "dossiers.json"
    public_dossier.write_text('{"stale":true}', encoding="utf-8")

    with pytest.raises(ProjectionDriftError, match="dossier twin differs"):
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
    html.write_text("<main>legacy</main>" + ("x" * 250_001), encoding="utf-8")

    with pytest.raises(ProjectionDriftError, match="exceeds 250000 bytes"):
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
    rebase = source.index("git pull --rebase --autostash -X theirs origin main")
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
        "scripts/check_government_revenue_projection.py",
        "scripts/inject_data_base.py",
        "scripts/externalize_css.py",
        "scripts/optimize_assets.py",
        "scripts/check_template_site_sync.py",
    ):
        assert path in guarded_inputs
