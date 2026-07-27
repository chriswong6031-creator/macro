"""Regression tests for the dedicated Divergence Radar page bootstrap."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_radar_page_waits_for_deferred_panel_before_rendering() -> None:
    """The asset sweep defers radar_panel.js, so startup must wait for DOM ready."""
    for rel in ("templates/radar.html.j2", "site/radar.html"):
        html = (ROOT / rel).read_text(encoding="utf-8")
        panel_at = html.index('src="radar_panel.js')
        ready_at = html.index('window.addEventListener("DOMContentLoaded"')
        render_at = html.index('window.renderRadarFull({ base: "basketdata/" });')

        assert panel_at < ready_at < render_at
        assert "<script>renderRadarFull(" not in html


def test_committed_radar_page_carries_the_deferred_asset_shape() -> None:
    html = (ROOT / "site" / "radar.html").read_text(encoding="utf-8")
    panel_tag = html[html.index('<script src="radar_panel.js'):].split("</script>", 1)[0]
    assert " defer" in panel_tag
