from pathlib import Path

from scripts.check_crypto_shelves import audit_text


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "vector.html.j2"


def test_wave1_structure_is_exact_and_verdict_is_singular():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert audit_text(
        source,
        tuple(f"S{i}" for i in range(1, 7)),
        1,
    ) == []


def test_wave1_uses_house_theme_and_signal_ink_without_legacy_skin_or_plotly():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert 'href="theme.css"' in source
    assert 'href="illus.css"' in source
    assert 'src="illus.js"' in source
    assert "_vector_polish" not in source
    assert "_plotly_head" not in source
    assert "Plotly" not in source


def test_wave1_keeps_both_advanced_interactive_instruments():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="vtm"' in source
    assert 'id="vtm-canvas"' in source
    assert 'src="vector_timemachine.js?v=2"' in source
    assert 'id="vec-risk-chart"' in source
    assert 'src="lightweight-charts-v5.js"' in source
    assert 'src="vector_chart.js"' in source


def test_wave1_front_door_avoids_banned_internal_language_and_alert_chrome():
    source = TEMPLATE.read_text(encoding="utf-8").lower()
    for banned in ("validated", "falsifier", "refuted", "证伪"):
        assert banned not in source
    assert "recent alerts" not in source
    assert 'href="alerts.html"' in source


def test_wave1_has_exactly_six_driver_rows_by_contract_loop():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert "{% for row in presentation.axes %}" in source
    builder = (ROOT / "scripts" / "build_vector.py").read_text(encoding="utf-8")
    assert "COCKPIT_AXIS_PRESENTATION" in builder


def test_wave1_arms_payload_budget_and_desktop_nav_containment():
    source = TEMPLATE.read_text(encoding="utf-8")
    builder = (ROOT / "scripts" / "build_vector.py").read_text(encoding="utf-8")
    assert "nth-last-child(3)" in source
    assert 're.sub(r">\\s+<", "> <", html)' in builder
    assert 'len(html.encode("utf-8"))' in builder
