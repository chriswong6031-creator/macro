from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from collectors.intl_macro import IntlMacroAdapter
from engine.international_macro_dashboard import (
    REGIONS,
    ROUTES,
    SCHEMA,
    build_country_view,
    decision_score,
    validate_view,
)

ROOT = Path(__file__).resolve().parents[1]


def _record(cc: str, *, missing: bool = False) -> dict:
    spec = REGIONS[cc]
    return {
        "cc": cc,
        "name": {
            "JP": "Japan",
            "KR": "South Korea",
            "EZ": "Euro Area",
            "GB": "United Kingdom",
            "IN": "India",
        }[cc],
        "name_zh": spec.scope_zh[:2],
        "flag": "🌐",
        "date": "2026-07-30",
        "quad": "Q2",
        "quad_name": "Reflation",
        "growth_score": 0.4,
        "inflation_score": 0.25,
        "confidence": 0.55,
        "liquidity": "neutral",
        "recession_score": 20.0,
        "recession_band": "low",
        "data_limited": missing,
        "macro": {
            "cpi_yoy": None if missing else 2.4,
            "gdp_yoy": None if missing else 1.8,
            "unemployment": None if missing else 4.1,
            "yield_10y": 3.2,
            "policy_rate": 2.5,
            "curve": 0.7,
            "fx": 100.25,
            "fx_strength_3m": -1.2,
            "drawdown": -5.0,
            "realvol": 18.0,
        },
        "macro_asof": {
            "cpi_yoy": None if missing else "2026-06",
            "gdp": None if missing else "2026-04",
            "unemployment": None if missing else "2026-06",
            "yield_10y": "2026-07",
        },
        "equity": {"drawdown_risk": 32.0},
        "risk_radar": {
            "state": "caution",
            "top_score": 62,
            "dominant_label_en": "Rate shock",
            "dominant_label_zh": "利率冲击",
            "drawdown_prob": {
                "h21": 0.21,
                "measure": ">=5% pullback within 21 business days",
            },
            "scares": [],
        },
    }


def _history() -> pd.DataFrame:
    index = pd.bdate_range("2026-05-01", periods=70)
    return pd.DataFrame(
        {
            "growth_score": [0.2] * 70,
            "inflation_score": [0.1] * 70,
            "recession_score": [15.0] * 70,
            "liquidity": ["neutral"] * 70,
        },
        index=index,
    )


def test_five_routes_are_unique_and_regional_lenses_are_explicit() -> None:
    assert ROUTES == {
        "JP": "japan.html",
        "KR": "south_korea.html",
        "EZ": "euro_area.html",
        "GB": "united_kingdom.html",
        "IN": "india.html",
    }
    assert len(set(ROUTES.values())) == 5
    lens_keys = {cc: {lens.key for lens in spec.lenses} for cc, spec in REGIONS.items()}
    assert "tankan" in lens_keys["JP"]
    assert "exports" in lens_keys["KR"]
    assert "spreads" in lens_keys["EZ"]
    assert "housing" in lens_keys["GB"]
    assert "monsoon" in lens_keys["IN"]
    assert len({tuple(sorted(keys)) for keys in lens_keys.values()}) == 5


def test_decision_score_is_bounded_deterministic_and_not_the_calibrated_probability() -> (
    None
):
    record = _record("JP")
    first, parts = decision_score(record)
    second, _ = decision_score(record)
    assert first == second
    assert 0 <= first <= 100
    assert round(sum(parts.values())) == first
    view = build_country_view(record, _history(), today=date(2026, 7, 30))
    assert view["decision"]["score"] == first
    assert view["risk"]["h21"] == pytest.approx(0.21)
    assert "not a forecast" in view["decision"]["method_en"]
    assert view["history"]["values"] and len(view["history"]["values"]) == 60


def test_missing_release_stays_missing_and_stale_release_is_named() -> None:
    missing = build_country_view(_record("IN", missing=True), today=date(2026, 7, 30))
    assert missing["regime"]["data_limited"] is True
    assert {item["state"] for item in missing["health"]} >= {"missing"}
    cpi = next(metric for metric in missing["metrics"] if metric["key"] == "cpi_yoy")
    assert cpi["raw"] is None
    assert cpi["value"] == "Unavailable"

    stale_record = _record("JP")
    stale_record["macro_asof"]["cpi_yoy"] = "2021-06"
    stale = build_country_view(stale_record, today=date(2026, 7, 30))
    cpi_health = next(item for item in stale["health"] if item["metric"] == "cpi_yoy")
    assert cpi_health["state"] == "stale"
    assert cpi_health["age_days"] > 1000


def test_view_contract_and_event_outcome_states() -> None:
    for cc in REGIONS:
        view = build_country_view(_record(cc), _history(), today=date(2026, 7, 30))
        validate_view(view)
        assert view["schema"] == SCHEMA
        assert view["route"] == ROUTES[cc]
        assert view["sources"]
        assert view["lenses"]
        assert all(
            event["state"] in {"released", "today", "upcoming"}
            for event in view["events"]
        )
        assert all("source" in event for event in view["events"])
    euro = build_country_view(_record("EZ"), today=date(2026, 7, 30))
    assert "EA21" in euro["scope_en"]
    assert "European Union" in euro["scope_en"]


def test_jsonstat_parser_preserves_release_period_and_values() -> None:
    payload = {
        "id": ["geo", "time"],
        "size": [1, 3],
        "value": {"0": 6.4, "1": 6.3, "2": 6.2},
        "dimension": {
            "time": {"category": {"index": {"2026-04": 0, "2026-05": 1, "2026-06": 2}}}
        },
    }
    series = IntlMacroAdapter._jsonstat_series(payload)
    assert list(series.index) == list(
        pd.to_datetime(["2026-04-01", "2026-05-01", "2026-06-01"])
    )
    assert list(series) == [6.4, 6.3, 6.2]


class _Response:
    def __init__(self, text: str, url: str = "https://official.example/series") -> None:
        self.text = text
        self.url = url


def test_official_ecb_parser_checks_units_and_records_provenance(monkeypatch) -> None:
    adapter = object.__new__(IntlMacroAdapter)
    adapter.cfg = {"retries": 1}
    adapter.source_meta = {}
    response = _Response(
        "TIME_PERIOD,OBS_VALUE,UNIT\n2026-07-29,2.00,PCPA\n2026-07-30,1.75,PCPA\n"
    )
    monkeypatch.setattr(adapter, "http_get", lambda *args, **kwargs: response)
    spec = {
        "provider": "ecb",
        "series_key": "FM.TEST",
        "unit": "PCPA",
        "release_period_semantics": "Daily effective observation",
    }
    frame = adapter._fetch_official("ez_depo_rate", spec)
    assert frame.iloc[-1, 0] == pytest.approx(1.75)
    assert adapter.source_meta["ez_depo_rate"]["status"] == "official"
    assert adapter.source_meta["ez_depo_rate"]["unit"] == "PCPA"

    with pytest.raises(ValueError, match="unit mismatch"):
        adapter._fetch_official("bad", {**spec, "unit": "INDEX"})


def test_shared_template_has_dark_mobile_dialog_and_accessibility_hooks() -> None:
    template = (ROOT / "templates" / "international_macro.html.j2").read_text()
    assert 'html[data-theme="light"] body.imd-page' in template
    assert "@media(max-width:760px)" in template
    assert "prefers-reduced-motion" in template
    assert 'role="dialog"' in template
    assert 'aria-modal="true"' in template
    assert "e.key==='Escape'" in template
    assert "document.activeElement===end" in template
    assert "data-close" in template
    assert "Prophet" not in template


def test_builder_renders_all_five_routes_from_one_template(
    tmp_path, monkeypatch
) -> None:
    from scripts import build_international_macro as builder

    latest = {"records": [_record(cc) for cc in REGIONS]}
    monkeypatch.setattr(
        builder.config,
        "load",
        lambda: {
            "storage": {"site_dir": str(tmp_path), "data_dir": str(tmp_path / "data")}
        },
    )
    monkeypatch.setattr(builder, "load_history", lambda _cc: _history())
    outputs = builder.build_all(latest)
    assert {path.name for path in outputs} == set(ROUTES.values())
    for route in ROUTES.values():
        html = (tmp_path / route).read_text()
        assert "International macro command center" in html
        assert 'class="imd-dlg"' in html
        assert (
            "Source health &amp; data contract" not in html
        )  # autoescape is intentionally off
        assert "Source health & data contract" in html


def test_navigation_uses_static_registry_and_has_no_placeholder_anchors() -> None:
    nav = (ROOT / "templates" / "_navlinks.html.j2").read_text()
    runtime = (ROOT / "templates" / "nav_market.js").read_text()
    served_runtime = (ROOT / "site" / "nav_market.js").read_text()
    for key, route in {
        "jp": "japan.html",
        "kr": "south_korea.html",
        "ez": "euro_area.html",
        "gb": "united_kingdom.html",
        "in": "india.html",
    }.items():
        assert f'data-intl-country="{key}"' in nav
        assert route in nav
        assert f"intlCountryHref('{key}', '{route}')" in runtime
    assert "intl.html#japan" not in runtime
    assert "intl.html#south-korea" not in runtime
    assert "intl.html#europe" not in runtime
    assert "intl.html#united-kingdom" not in runtime
    assert "intl.html#india" not in runtime
    assert runtime == served_runtime


def test_generated_routes_are_checked_in_and_match_contract() -> None:
    for cc, route in ROUTES.items():
        page = ROOT / "site" / route
        payload = ROOT / "data" / "international_macro" / f"{cc}_latest.json"
        assert page.exists()
        assert payload.exists()
        assert json.loads(payload.read_text())["schema"] == SCHEMA
        html = page.read_text()
        assert "imd-score-" in html
        assert "International macro command center" in html
