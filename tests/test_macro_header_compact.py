"""Regression coverage for the Macro dashboard's compact glance layer."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
DASHBOARD = TEMPLATES / "dashboard.html.j2"
SOURCE = DASHBOARD.read_text(encoding="utf-8")


def _glance_source() -> str:
    start = SOURCE.index('<div class="mx5-sc-left">')
    end = SOURCE.index("</div>{# /mx5-sc-left #}", start)
    return SOURCE[start:end]


def test_macro_header_has_no_always_visible_explainer_blocks():
    """Dense regime/risk receipts must not return to the front dashboard."""

    glance = _glance_source()
    for removed in (
        "mx5-rgx",
        "mx5-chipn",
        "mx5-score-prov",
        "Model odds",
        "Opposite scales",
        "Measured at this state",
        "Six-signal blend",
    ):
        assert removed not in glance


def test_macro_header_keeps_detail_on_demand():
    """Compactness must not remove the existing regime and risk drill-downs."""

    glance = _glance_source()
    assert 'id="mx5FlipCtxPop"' in glance
    assert 'onclick="mx5OpenDlg(\'dlg-risk\')"' in glance
    assert "The dial is capped at " in glance
    assert "six-signal blend is " in glance


def test_dashboard_template_still_compiles():
    Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=False,
    ).get_template("dashboard.html.j2")
