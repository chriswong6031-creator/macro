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


def test_workflow_is_scheduled_off_render_and_handles_only_safe_cas_conflict() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/company-intelligence.yml").read_text(encoding="utf-8")
    assert 'cron: "17 */3 * * *"' in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "python -m scripts.refresh_company_intelligence" in workflow
    assert 'if [ "$rc" -eq 2 ]' in workflow
    assert "R2_SECRET_ACCESS_KEY" in workflow
