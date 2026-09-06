"""Tests for engine/valuation_scenario.py (FROZEN SPEC B-F07-1)."""
from __future__ import annotations

import re
from pathlib import Path

from engine import valuation_scenario as vs

ROOT = Path(__file__).resolve().parent.parent

FIXTURE_ROW = {
    "fy": 2025,
    "period_end": "2025-09-27",
    "revenue": 4.16e11,
    "op_income": 1.28e11,
    "net_income": 1.05e11,
    "cash": 3.2e10 + 1.0e10,  # arbitrary; net_debt derived below
    "debt_lt": 8.0e10,
    "debt_cur": 1.0e10,
    "shares": 1.49e10,
}


def _rows(**overrides):
    row = dict(FIXTURE_ROW)
    row.update(overrides)
    return [row]


def test_math_matches_frozen_formula():
    blob = vs.compute(_rows(), price=319.97, asof="2026-09-05", ticker="AAPL")
    assert blob is not None
    by_key = {s["key"]: s for s in blob["scenarios"]}
    net_income = FIXTURE_ROW["net_income"]
    revenue = FIXTURE_ROW["revenue"]
    shares = FIXTURE_ROW["shares"]
    net_margin_base = net_income / revenue
    for key, g, m_pp, mult in vs.SCENARIOS:
        adj = net_income * (1 + g / 100.0) * (1 + (m_pp / 100.0) / net_margin_base)
        expected = round((adj * mult) / shares, 2)
        got = by_key[key]
        assert got["computable"] is True
        assert got["per_share"] == expected, (key, got["per_share"], expected)


def test_null_propagation():
    blob = vs.compute(_rows(net_income=None))
    for s in blob["scenarios"]:
        assert s["computable"] is False
        assert s["per_share"] is None
        assert s["missing"] == ["net_income"]
    assert blob["base"]["net_income"]["value"] is None
    assert blob["base"]["net_income"]["reported"] is False

    blob2 = vs.compute(_rows(cash=None))
    assert blob2["base"]["net_debt"]["value"] is None
    assert blob2["base"]["net_debt"]["reported"] is False
    for s in blob2["scenarios"]:
        assert s["computable"] is False
        assert "net_debt" in s["missing"]

    # No zero substitution anywhere for the dropped inputs.
    assert blob["base"]["net_income"]["value"] != 0
    assert blob2["base"]["net_debt"]["value"] != 0


def test_share_count_identity_is_declared():
    blob = vs.compute(_rows())
    assert blob["base"]["share_count"]["identity"] == "outstanding"
    assert blob["base"]["share_count"]["identity"] != "diluted"


def test_period_and_unit_consistency():
    blob = vs.compute(_rows(revenue_fy=2024))
    for s in blob["scenarios"]:
        assert s["computable"] is False
        assert s["missing"] == ["consistent period"]
    assert blob["base"]["revenue"]["unit"] == "USD"
    assert blob["base"]["share_count"]["unit"] == "shares"


def test_negative_or_zero_earnings_is_not_a_value():
    blob = vs.compute(_rows(net_income=0))
    for s in blob["scenarios"]:
        assert s["computable"] is False
        assert s["per_share"] is None
        assert "positive reported earnings" in s["missing"]

    blob2 = vs.compute(_rows(net_income=-5.0))
    for s in blob2["scenarios"]:
        assert s["computable"] is False
        assert s["per_share"] is None


def test_module_is_pure():
    src = (ROOT / "engine" / "valuation_scenario.py").read_text()
    for banned in ("open(", "requests", "read_parquet", "datetime.now", "Path("):
        assert banned not in src, banned


BANNED_VOCAB = [
    "probability", "confidence", "likely", "odds", "expected value",
    "fair value", "price target", "consensus", "analyst", "estimate",
    "forecast", "validated",
    "概率", "置信", "目标价", "共识", "预测",
]


def test_no_banned_vocabulary():
    partial = ROOT / "templates" / "_valuation_scenario.html.j2"
    text = partial.read_text().lower()
    for word in BANNED_VOCAB:
        assert word.lower() not in text, f"banned word {word!r} found in partial"


def test_bilingual_parity():
    partial = ROOT / "templates" / "_valuation_scenario.html.j2"
    text = partial.read_text()
    for m in re.finditer(r"t\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)", text):
        en, zh = m.group(1), m.group(2)
        assert zh.strip() != "", f"empty ZH for en={en!r}"
    for m in re.finditer(r'title="[^"]*[一-鿿][^"]*"', text):
        raise AssertionError(f"ZH text found in a title= attribute: {m.group(0)!r}")


def test_panel_renders_and_omits():
    import jinja2

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")))
    env.globals["t"] = lambda en, zh: en

    tmpl_src = (
        "{% include '_valuation_scenario.html.j2' %}"
    )
    tmpl = env.from_string(tmpl_src)

    computable_blob = vs.compute(_rows(), price=319.97, asof="2026-09-05", ticker="AAPL")
    html = tmpl.render(valuation_scenario=computable_blob, deep_ids=[])
    assert 'id="valuation-scenario"' in html
    assert 'data-valuation-scenario="v1"' in html

    null_blob = vs.compute(_rows(net_income=None), ticker="AAPL")
    assert null_blob["any_computable"] is False
    html2 = tmpl.render(valuation_scenario=null_blob, deep_ids=[])
    assert 'id="valuation-scenario"' in html2
    assert "Can't be computed without reported net income" in html2
    assert "not reported" in html2
    # No raw internal field slug leaked into the null copy.
    for raw_slug in ("net_income", "net_debt", "net_margin_base", "share_count"):
        assert raw_slug not in html2

    # A blob with nothing computed AND no base data at all still must not
    # render an empty/broken section -- compute() only returns None when
    # there is no dated row at all, which the template also guards.
    assert vs.compute([]) is None


def test_research_display_only_line_present():
    import jinja2

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")))
    env.globals["t"] = lambda en, zh: f"{en}|{zh}"
    tmpl = env.from_string("{% include '_valuation_scenario.html.j2' %}")
    blob = vs.compute(_rows(), price=319.97, asof="2026-09-05", ticker="AAPL")
    html = tmpl.render(valuation_scenario=blob, deep_ids=[])
    assert "Research display only" in html
    assert "仅供研究展示" in html
