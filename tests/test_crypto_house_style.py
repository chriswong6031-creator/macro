from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PARTIAL = ROOT / "templates" / "_crypto_house_style.html.j2"


def test_both_crypto_dashboards_use_one_house_style_partial():
    for template in ("crypto.html.j2", "vector.html.j2"):
        source = (ROOT / "templates" / template).read_text(encoding="utf-8")
        assert '{% include "_crypto_house_style.html.j2" %}' in source


def test_house_style_uses_sf_display_and_inter_ui_data():
    source = PARTIAL.read_text(encoding="utf-8")
    assert '"SF Pro Display"' in source
    assert '"SF Pro Text"' in source
    assert "--font-data: Inter" in source
    assert "--font-mono: var(--font-data)" in source
    assert "--num: var(--font-data)" in source


def test_house_style_inherits_macro_and_commodities_tokens():
    source = PARTIAL.read_text(encoding="utf-8")
    for token in (
        "var(--info)",
        "var(--panel)",
        "var(--panel2)",
        "var(--line)",
        "var(--text)",
        "var(--muted)",
    ):
        assert token in source
    assert "--crypto: var(--info)" in source
    assert "border-radius: 16px" in source
    assert "backdrop-filter: saturate(165%) blur(18px)" in source
