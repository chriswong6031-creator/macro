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


def _radar_record(cc: str, **radar) -> dict:
    """A record whose nightly risk_radar_intl snapshot carries firing legs."""
    record = _record(cc)
    record["risk_radar"] = {
        "state": "caution",
        "market": cc.lower(),
        "top_score": 62,
        "dominant_label_en": "Parabolic extension / exhaustion",
        "dominant_label_zh": "抛物线伸展／透支",
        "gross_factor": 0.9,
        "drawdown_prob": {"h5": 0.05, "h10": 0.12, "h21": 0.21, "base_h21": 0.14,
                          "lift_h21": 1.5, "measure": ">=5% pullback within 21 business days"},
        "scares": [
            {
                "scare": "extension",
                "tier": "A",
                "label_en": "Parabolic extension / exhaustion",
                "label_zh": "抛物线伸展／透支",
                "score": 80.0,
                "band": "caution",
                "firing_legs": [{"leg": "ext_etf", "pctile": 0.89, "confirmed": True}],
            }
        ],
        **radar,
    }
    return record


def _render_jp(builder, tmp_path, records: list[dict]) -> str:
    builder.build_all({"records": records})
    return (tmp_path / ROUTES["JP"]).read_text()


def test_risk_radar_card_renders_from_the_snapshot_and_is_absent_without_one(
    tmp_path, monkeypatch
) -> None:
    """The shared .rrx card is the international boards' radar layer, and it is the ONLY
    place the 21-session number appears once it renders. A market with no usable snapshot
    (first run, or a profile that raised inside engine/intl_run.py) must keep the page it
    has today rather than fail or empty it."""
    from scripts import build_international_macro as builder

    monkeypatch.setattr(
        builder.config,
        "load",
        lambda: {
            "storage": {"site_dir": str(tmp_path), "data_dir": str(tmp_path / "data")}
        },
    )
    monkeypatch.setattr(builder, "load_history", lambda _cc: _history())

    html = _render_jp(builder, tmp_path, [_radar_record(cc) for cc in REGIONS])
    assert 'class="rrx ' in html                      # shared card markup
    assert ".rrx .rrx-badge" in html                  # shared card CSS came with it
    assert ".help .tip{display:none" in html          # tooltip bodies stay hidden pre-JS
    assert "Pullback risk" in html and "回撤风险" in html
    # The bare glance-tier prints of the same constant fold into the card: neither the
    # trust tile nor the risk command card repeats it. Only the Tier-3 dialog receipt
    # (which adds the calibration measure) still carries the raw figure — exactly once.
    trust = html.split('class="imd-trust"', 1)[1].split("</section>", 1)[0]
    assert "21-session pullback" not in trust
    face = html.split('data-dialog="dlg-risk"', 1)[1].split("</button>", 1)[0]
    assert "21.0%" not in face and "Active scare families" in face
    assert html.count("21.0%") == 1
    # firing-leg codes reach the glance tier as plain words, never as engine slugs
    assert "Market ETF stretched vs 200-day" in html
    assert "市场ETF超买" in html
    assert ">ext_etf<" not in html

    # no snapshot at all -> no card, and the page keeps its own pullback tile
    bare = []
    for cc in REGIONS:
        record = _record(cc)
        record.pop("risk_radar")
        bare.append(record)
    html = _render_jp(builder, tmp_path, bare)
    assert 'class="rrx ' not in html
    assert "21-session pullback" in html.split('class="imd-trust"', 1)[1]
    assert "International macro command center" in html

    # snapshot present but with no calibrated odds -> same absent-safe fallback
    html = _render_jp(
        builder, tmp_path, [_radar_record(cc, drawdown_prob={}) for cc in REGIONS]
    )
    assert 'class="rrx ' not in html
    assert "21-session pullback" in html.split('class="imd-trust"', 1)[1]


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
