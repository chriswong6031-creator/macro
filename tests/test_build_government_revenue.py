"""Builder ownership and fail-soft integration tests for Government Revenue."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from scripts import build_baskets, build_government_revenue


def _payload() -> dict:
    return {
        "schema_version": "company_government_revenue.v1",
        "as_of": "2026-08-01",
        "known_at": "2026-08-01T08:00:00Z",
        "authority": {"tier": "display", "can_rank": False},
        "coverage": {"entities_mapped": 1},
        "market": {},
        "companies": [{"ticker": "LMT", "name": "Lockheed Martin", "metrics": {}}],
    }


def test_builder_writes_canonical_site_twin_and_page(tmp_path: Path, monkeypatch) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<title>Government Revenue</title><script>{{ payload_json|safe }}</script>",
        encoding="utf-8",
    )
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())

    html, canonical, site_json = build_government_revenue.build(tmp_path)

    assert html.exists() and canonical.exists() and site_json.exists()
    assert canonical.read_bytes() == site_json.read_bytes()
    assert json.loads(canonical.read_text())["companies"][0]["ticker"] == "LMT"
    assert "Government Revenue" in html.read_text()


def test_baskets_wrapper_logs_subbuilder_failure_without_parsing_parent_argv(
    monkeypatch, caplog,
) -> None:
    def fail(_root):
        raise RuntimeError("synthetic builder failure")

    monkeypatch.setattr(build_government_revenue, "build", fail)
    with caplog.at_level(logging.ERROR):
        ok = build_baskets._build_government_revenue_workbench()

    assert ok is False
    assert "synthetic builder failure" in caplog.text
