from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "render.yml"
).read_text()


def test_render_workflow_has_an_international_scope():
    assert "options: [all, macro, intl," in WORKFLOW
    assert "templates/intl.html.j2|scripts/build_intl.py) echo intl;;" in WORKFLOW
    assert "for R in macro intl china hk canada markets gex baskets sits; do" in WORKFLOW
    assert 'scripts.build_intl; }' in WORKFLOW
    assert "intl)\n              intl ;;" in WORKFLOW


def test_full_render_includes_international_dashboard():
    assert (
        "spine; intl; canada; band; central; flowleaders; leaderradar; "
        "foresightpage; hub; crypto; us_pages; libs; sits; csits ;;"
    ) in WORKFLOW
