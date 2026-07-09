"""Tests for collectors/hk_names_zh.py — Chinese name enricher."""
import pytest
from collectors.hk_names_zh import load_names_zh


def test_load_returns_dict():
    names = load_names_zh()
    assert isinstance(names, dict), "load_names_zh should return a dict"


def test_no_comment_keys():
    names = load_names_zh()
    for k in names:
        assert not k.startswith("_"), f"Private key leaked into output: {k!r}"


def test_bottomwatch_largecaps_resolved():
    """The 4 Bottom-Watch large-caps explicitly called out in the brief must resolve."""
    names = load_names_zh()
    expected = {
        "0358.HK": "江西铜业",
        "0017.HK": "新世界发展",
        "2600.HK": "中国铝业",
        "3993.HK": "洛阳钼业",
    }
    for ticker, zh_name in expected.items():
        assert ticker in names, f"Missing ticker {ticker} in names_zh"
        assert names[ticker] == zh_name, (
            f"Wrong Chinese name for {ticker}: got {names[ticker]!r}, expected {zh_name!r}"
        )


def test_ticker_format():
    """All keys should be NNN.HK format (4-digit padded code + .HK)."""
    names = load_names_zh()
    for k in names:
        parts = k.split(".")
        assert len(parts) == 2 and parts[1] == "HK", f"Bad ticker format: {k!r}"
        assert 3 <= len(parts[0]) <= 5, f"Code length unexpected: {k!r}"


def test_non_empty_values():
    """All values should be non-empty strings."""
    names = load_names_zh()
    assert len(names) > 0, "names_zh map is empty"
    for k, v in names.items():
        assert isinstance(v, str) and v.strip(), f"Empty/invalid value for {k!r}: {v!r}"


def test_command_panel_scorecards_include_name_zh():
    """_build_scorecards passes name_zh through from washout_watch rows."""
    from engine.hk_command_panel import _build_scorecards
    setups = {
        "washout_watch": [
            {
                "ticker": "0700.HK",
                "name": "Tencent",
                "name_zh": "腾讯控股",
                "state": "washout_watch",
                "confluence_signals": ["RSI < 30", "dist_200dma < -0.3"],
                "knife_risk": False,
            }
        ]
    }
    bw, cw = _build_scorecards(setups)
    assert len(bw) == 1
    assert bw[0]["name_zh"] == "腾讯控股", f"name_zh not propagated: {bw[0]}"
    assert bw[0]["name"] == "Tencent"


def test_command_panel_no_english_in_zh_details():
    """Force detail_zh strings must not contain raw English freshness states."""
    from engine.hk_command_panel import _adr_force, _cbbc_force, _narrative_force

    # ADR stale — detail_zh must not contain 'stale' or 'dead'
    result = _adr_force({"freshness_verdict": "stale", "composite": {}})
    assert "stale" not in result["detail_zh"], f"English 'stale' leaked into ZH: {result['detail_zh']!r}"
    assert "dead" not in result["detail_zh"], f"English 'dead' leaked into ZH: {result['detail_zh']!r}"

    result_dead = _adr_force({"freshness_verdict": "dead", "composite": {}})
    assert "dead" not in result_dead["detail_zh"], f"English 'dead' leaked: {result_dead['detail_zh']!r}"

    # Narrative stale
    result_narr = _narrative_force({"freshness": "stale", "entities": []})
    assert "stale" not in result_narr["detail_zh"]
    assert "missing" not in result_narr["detail_zh"]

    # CBBC missing
    result_cbbc = _cbbc_force({"freshness": "missing", "bellwethers": []})
    assert "missing" not in result_cbbc["detail_zh"]
