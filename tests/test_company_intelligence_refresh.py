from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from scripts import refresh_company_intelligence as refresh


class _Response(io.BytesIO):
    def close(self) -> None:  # closing() requires close; BytesIO already does it.
        super().close()


def _opener(payload: dict):
    raw = json.dumps(payload).encode("utf-8")

    def open_index(_request, *, timeout: float):
        assert timeout > 0
        return _Response(raw)

    return open_index


def test_fetch_transcript_index_requires_terminal_v1_commit_marker(tmp_path: Path) -> None:
    payload = {
        "schema": "mastermind.tx-index/v1",
        "symbols": {"NVDA": ["2026Q1"]},
        "revisions": {},
        "dates": {"NVDA/2026Q1": "2026-05-20"},
        "body_count": 1,
        "symbol_count": 1,
        "generated_at": "2026-05-20T00:00:00Z",
    }
    target = tmp_path / "tx-index.json"
    written = refresh.fetch_transcript_index("https://example.test/index.json", target, opener=_opener(payload))
    assert written == payload
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_fetch_transcript_index_refuses_invalid_marker_without_writing(tmp_path: Path) -> None:
    target = tmp_path / "tx-index.json"
    with pytest.raises(refresh.RefreshError, match="invalid"):
        refresh.fetch_transcript_index(
            "https://example.test/index.json",
            target,
            opener=_opener({"schema": "wrong", "symbols": {}}),
        )
    assert not target.exists()


def test_refresh_fails_closed_when_fail_soft_earnings_fetch_materializes_nothing(tmp_path: Path) -> None:
    # fetch_earnings_scores intentionally returns zero for an absent source so
    # the render can preserve its prior state. The publisher must not mistake
    # that zero for safe input and replace its public root marker.
    with pytest.raises(refresh.RefreshError, match="earnings manifest unavailable"):
        refresh.refresh(tmp_path, fetch_scores=lambda **_kwargs: 0)


def test_refresh_can_preserve_a_validated_output_tree_for_a_post_ci_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sidecar must read CIE before TemporaryDirectory cleanup occurs."""
    output = tmp_path / "persistent-output"
    seen: dict[str, Path] = {}
    monkeypatch.setattr(refresh, "ensure_earnings_inputs", lambda _source: {})
    monkeypatch.setattr(refresh, "fetch_transcript_index", lambda _url, destination: destination.write_text("{}"))

    def build(argv: list[str]) -> int:
        target = Path(argv[argv.index("--out-dir") + 1])
        target.mkdir(parents=True)
        (target / "manifest.json").write_text("{}")
        seen["build"] = target
        return 0

    monkeypatch.setattr(refresh, "build_company_intelligence", build)
    monkeypatch.setattr(refresh, "validate_generation", lambda path: {"status": "ready", "generation_id": "a" * 24, "company_count": 1, "event_count": 1, "warnings": []})

    def publish(path: Path, **_kwargs) -> int:
        seen["publish"] = path
        assert (path / "manifest.json").is_file()
        return 0

    assert refresh.refresh(
        tmp_path / "work",
        out_dir=output,
        fetch_scores=lambda **_kwargs: 0,
        publish_generation=publish,
    ) == 0
    assert seen == {"build": output, "publish": output}


def test_workflow_is_scheduled_off_render_and_handles_only_safe_cas_conflict() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/company-intelligence.yml").read_text(encoding="utf-8")
    assert 'cron: "17 */3 * * *"' in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "python -m scripts.refresh_company_intelligence" in workflow
    assert 'if [ "$rc" -eq 2 ]' in workflow
    assert "R2_SECRET_ACCESS_KEY" in workflow
    assert "--out-dir \"$OUTPUT_DIR\"" in workflow
    assert "python -m scripts.build_company_theme_exposure" in workflow
    assert "python -m scripts.publish_company_theme_exposure_r2" in workflow
    assert 'if [ "$side_rc" -eq 2 ]' in workflow
    assert "timeout-minutes: 25" in workflow


def test_scheduled_workflow_contains_its_sparse_import_closure() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/company-intelligence.yml").read_text(encoding="utf-8")
    assert "lib/config.py" in workflow
    install_line = next(line for line in workflow.splitlines() if "pip install --quiet" in line)
    assert "pyyaml" in install_line
    assert "requests" in install_line
    for path in (
        "engine/company_theme_exposure",
        "scripts/build_company_theme_exposure.py",
        "scripts/publish_company_theme_exposure_r2.py",
        "data/baskets/membership.json",
        "config/theme_crosswalk.yml",
        "data/neuralweb/theme_state.json",
    ):
        assert path in workflow
