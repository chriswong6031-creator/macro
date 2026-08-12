"""Express-render ownership and data-pristine mode for China Policy Watch."""
from __future__ import annotations

from pathlib import Path

from scripts import build_china_policy_watch as builder


ROOT = Path(__file__).resolve().parents[1]
EXPRESS_LANES = (
    ROOT / ".github" / "workflows" / "render.yml",
    ROOT / ".github" / "workflows" / "engine-render.yml",
)


def test_site_only_cli_does_not_request_a_data_write(monkeypatch):
    seen: list[bool] = []
    monkeypatch.setattr(builder, "build", lambda *, site_only=False: seen.append(site_only))

    assert builder.main(["--site-only"]) == 0
    assert seen == [True]


def test_default_cli_preserves_the_asia_lane_data_contract(monkeypatch):
    seen: list[bool] = []
    monkeypatch.setattr(builder, "build", lambda *, site_only=False: seen.append(site_only))

    assert builder.main([]) == 0
    assert seen == [False]


def test_both_express_lanes_render_policy_watch_site_only():
    command = "scripts.build_china_policy_watch --site-only"
    for lane in EXPRESS_LANES:
        workflow = lane.read_text(encoding="utf-8")
        assert workflow.count(command) >= 2, (
            f"{lane.name} must own Policy Watch in all-scope and narrow China renders"
        )
        assert "cn_policy" in workflow.split('local ORDER="', 1)[1].split('"', 1)[0]


def test_render_trigger_and_scope_own_policy_watch_sources():
    workflow = EXPRESS_LANES[0].read_text(encoding="utf-8")
    assert '- "scripts/build_china_policy_watch.py"' in workflow
    assert "templates/china_policy_watch.html.j2" in workflow
    assert "scripts/build_china_policy_watch.py) echo china;;" in workflow
