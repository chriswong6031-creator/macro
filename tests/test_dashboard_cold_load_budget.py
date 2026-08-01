"""Cold-load contracts for the heavy regional macro dashboards."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
MACRO_TEMPLATES = (
    "dashboard.html.j2",
    "canada.html.j2",
    "china.html.j2",
    "hk.html.j2",
)


def test_hidden_heatmaps_are_loaded_on_demand() -> None:
    loader = (TEMPLATES / "_lazy_heatmap_loader.html.j2").read_text()
    assert "window.mmLoadHeatmap" in loader
    assert "if(pending)return pending" in loader
    assert "s.async=true" in loader
    assert "new URL('heatmap.js',document.baseURI)" in loader

    for name in MACRO_TEMPLATES:
        template = (TEMPLATES / name).read_text()
        assert '{% include "_lazy_heatmap_loader.html.j2" %}' in template
        assert '<script src="heatmap.js"></script>' not in template
        assert "window.mmLoadHeatmap" in template


def test_macro_pages_do_not_eager_load_feature_only_assets() -> None:
    dashboard = (TEMPLATES / "dashboard.html.j2").read_text()
    assert '<script src="onboard.js"></script>' not in dashboard
    assert '<link rel="stylesheet" href="onboard.css">' not in dashboard

    for name in ("china.html.j2", "hk.html.j2"):
        template = (TEMPLATES / name).read_text()
        assert (
            "{% if mode != 'macro' %}\n"
            '<script src="stocktable.js"></script>'
        ) in template
