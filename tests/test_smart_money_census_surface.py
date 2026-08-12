"""Focused contracts for the bounded 13F Census surface and canonical site build."""
from __future__ import annotations

import json
import math
import shutil
from copy import deepcopy
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from scripts import build_site
from scripts import build_smart_money as desk_builder

ROOT = Path(__file__).resolve().parents[1]


def _census_payload(n: int = 7) -> dict:
    def rows(prefix: str) -> list[dict]:
        return [
            {
                "ticker": f"{prefix}{i}",
                "name": f"Mapped {prefix}{i}",
                "issuer": f"Issuer {prefix}{i}",
                "sector": "Technology",
                "net_increasers": i + 1 if prefix == "B" else -(i + 1),
                "net_filer_delta": i + 1 if prefix == "B" else -(i + 1),
                "holder_delta": i if prefix == "B" else -i,
                "paired_observations": 100 + i,
                "new_filers": 10 + i,
                "adding_filers": 20 + i,
                "trimming_filers": 5 + i,
                "exiting_filers": 3 + i,
            }
            for i in range(n)
        ]

    def source(seed: str, *, with_overlay: bool = False) -> dict:
        value = {
            "byte_length": 1_000_000,
            "kind": "sec_form13f_bulk_filing_window",
            "quality_findings": {
                "confidential_omitted": 1,
                "duplicate_included_manager_sequence": 0,
                "included_manager_count_mismatch": 1,
                "rolling_overlay_catalog_only": 16,
                "rolling_overlay_excluded": 2,
                "table_entry_total_mismatch": 2,
                "table_value_total_mismatch": 3,
            },
            "sha256": seed * 64,
            "url": "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/fixture.zip",
            "official_reference_url": (
                "https://www.sec.gov/files/structureddata/data/"
                "form-13f-data-sets/fixture.zip"
            ),
            "filing_window_cutoff_at": "2026-05-29T21:30:00Z",
            "acquisition_mode": "sec_https",
            "official_source_status": "sec_https",
            "expected_sha256_attested": False,
        }
        if with_overlay:
            value["rolling_overlay"] = {
                "state": "applied",
                "generation_id": "i13fgen_" + "c" * 64,
                "manifest_sha256": "d" * 64,
                "catalog_source_cutoff_at": "2026-08-08T19:59:00Z",
                "requested_source_cutoff_at": "2026-08-08T20:00:00Z",
                "catalog_filings_through_cutoff": 596,
                "catalog_only_filings": 16,
                "bulk_duplicate_filings_verified": 580,
                "latest_known": True,
            }
        return value

    return {
        "schema": "institutional_13f.census_public/v1",
        "state": "rolling",
        "generated_at": "2026-08-08T20:00:00Z",
        "identity_grain": "filer",
        "periods": {"current": "2026-06-30", "baseline": "2026-03-31"},
        "coverage": {
            "current_original_filings": 596,
            "baseline_original_filings": 8741,
            "paired_filings": 580,
            "progress_pct": 6.8,
            "current_notice_filers": 12,
            "current_amendments": 4,
            "current_holding_filers": 584,
            "current_long_positions": 150000,
            "mapped_long_positions": 100000,
            "mapping_coverage_pct": 66.7,
            "value_unit_status": "excluded_mixed_reported_units",
            "current_quality_excluded_reports": 2,
            "baseline_quality_excluded_reports": 3,
            "current_quality_excluded_lineages": 1,
            "baseline_quality_excluded_lineages": 2,
            "current_overlapping_amendment_lineages": 1,
            "baseline_overlapping_amendment_lineages": 0,
            "share_factor_security_exclusions": 7,
            "structural_event_security_exclusions": 9,
        },
        "scope": {
            "population": "all_sec_13f_filers",
            "includes_passive_quant_custody": True,
            "skill_weighted": False,
            "comparison_basis": "same_filer_completed_quarters",
            "action_basis": "long_share_count_change",
            "reported_value_use": "excluded_until_unit_resolved",
            "corporate_action_filter": "holder_discontinuity_and_common_share_factor_v2",
            "materiality_threshold_pct": 5.0,
            "notices_are_zero_portfolios": False,
            "authority": "context_only",
        },
        "leaders": {"broadening": rows("B"), "narrowing": rows("N")},
        "sector_breadth": [
            {
                "sector": f"Sector {i}",
                "name": f"Sector {i}",
                "net_filer_delta": i - 3,
                "net_increasers": i - 3,
                "paired_observations": 500,
                "security_count": 40 + i,
            }
            for i in range(n)
        ],
        "freshness": {
            "as_of": "2026-08-08T20:00:00Z",
            "current_source": source("a", with_overlay=True),
            "baseline_source": source("b"),
            "identifier_resolution": {
                "resolved_cusips": 1776,
                "sha256": "e" * 64,
                "source": "openfigi_cusip_ticker_projection",
                "temporal_policy": "current_map_not_point_in_time",
                "venue_policy": "us_trading_venues_only",
            },
            "sector_classification": {
                "source": "fund_intelligence_current_classification_map",
                "sha256": "f" * 64,
                "temporal_policy": "current_map_not_point_in_time",
            },
            "duplicate_original_lineages": 0,
            "orphan_amendment_lineages": 0,
            "relationship_deduplication": "as_filed_filer_grain",
            "source_cutoff_at": "2026-08-08T20:00:00Z",
            "latest_known": True,
        },
    }


def _write_source(root: Path, payload: dict) -> Path:
    path = root / "data" / "institutional_13f" / "public" / "census_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")))
    return path


def test_census_publisher_bounds_lists_and_writes_the_embedded_object(tmp_path, monkeypatch):
    _write_source(tmp_path, _census_payload())
    monkeypatch.setattr(desk_builder.config, "ROOT", tmp_path)

    bounded = desk_builder._publish_institutional_census()
    published = json.loads(
        (tmp_path / "site" / "factordata" / "institutional_census_summary.json")
        .read_text()
    )

    assert published == bounded
    assert bounded["schema"] == "institutional_13f.census_public/v1"
    assert bounded["identity_grain"] == "filer"
    assert len(bounded["leaders"]["broadening"]) == 6
    assert len(bounded["leaders"]["narrowing"]) == 6
    assert len(bounded["sector_breadth"]) == 6
    assert "B6" not in json.dumps(bounded)


def test_census_boundary_fails_closed_on_schema_identity_or_size(tmp_path, monkeypatch):
    monkeypatch.setattr(desk_builder.config, "ROOT", tmp_path)

    wrong_schema = _census_payload(1)
    wrong_schema["schema"] = "institutional_13f.census_public/v0"
    _write_source(tmp_path, wrong_schema)
    assert desk_builder._load_institutional_census()["state"] == "degraded"

    wrong_identity = _census_payload(1)
    wrong_identity["identity_grain"] = "institution"
    _write_source(tmp_path, wrong_identity)
    rejected = desk_builder._load_institutional_census()
    assert rejected["state"] == "degraded"
    assert rejected["identity_grain"] == "filer"

    oversized = _census_payload(1)
    oversized["note"] = "x" * (desk_builder._CENSUS_MAX_RAW_BYTES + 100)
    _write_source(tmp_path, oversized)
    assert desk_builder._load_institutional_census()["reason"] == "source_rejected"


def test_census_boundary_rejects_private_or_unknown_nested_fields_and_bad_types(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(desk_builder.config, "ROOT", tmp_path)

    rejected_payloads = []
    for key, value in (
        ("manager_name", "Private Manager"),
        ("holdings", [{"ticker": "SECRET"}]),
        ("cusip", "123456789"),
    ):
        payload = deepcopy(_census_payload(1))
        payload["leaders"]["broadening"][0][key] = value
        rejected_payloads.append(payload)

    unknown_nested = deepcopy(_census_payload(1))
    unknown_nested["freshness"]["current_source"]["quality_findings"][
        "unknown_future_count"
    ] = 1
    rejected_payloads.append(unknown_nested)

    bool_count = deepcopy(_census_payload(1))
    bool_count["coverage"]["current_original_filings"] = True
    rejected_payloads.append(bool_count)

    string_metric = deepcopy(_census_payload(1))
    string_metric["leaders"]["broadening"][0]["paired_observations"] = "100"
    rejected_payloads.append(string_metric)

    invalid_overlay = deepcopy(_census_payload(1))
    invalid_overlay["freshness"]["current_source"]["rolling_overlay"][
        "latest_known"
    ] = "true"
    rejected_payloads.append(invalid_overlay)

    partial_provenance = deepcopy(_census_payload(1))
    del partial_provenance["freshness"]["current_source"]["filing_window_cutoff_at"]
    rejected_payloads.append(partial_provenance)

    for payload in rejected_payloads:
        _write_source(tmp_path, payload)
        rejected = desk_builder._load_institutional_census()
        assert rejected["state"] == "degraded"
        assert rejected["reason"] == "source_rejected"
        assert "Private Manager" not in json.dumps(rejected)


def test_census_boundary_rejects_duplicate_json_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(desk_builder.config, "ROOT", tmp_path)
    source = _write_source(tmp_path, _census_payload(1))
    source.write_text(
        '{"schema":"institutional_13f.census_public/v1",'
        '"schema":"institutional_13f.census_public/v1"}'
    )

    assert desk_builder._load_institutional_census()["reason"] == "source_rejected"


def test_census_render_only_replaces_just_desk_census_and_page(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "templates", tmp_path / "templates")
    factordata = tmp_path / "site" / "factordata"
    funddata = tmp_path / "site" / "funddata"
    factordata.mkdir(parents=True)
    funddata.mkdir(parents=True)
    _write_source(tmp_path, _census_payload(1))

    original_desk = {
        "built": "2026-08-08T10:00:00Z",
        "freshness": {"axes": []},
        "institutional_census": {
            "state": "complete",
            "leaders": {"broadening": [{"ticker": "OLD"}], "narrowing": []},
        },
        "wire": [{"ticker": "KEEP", "axis": "13dg"}],
        "follow": {"meta": {"n_follow": 1}},
        # Production desk artifacts retain legacy Python-JSON NaN sentinels.
        "legacy_nan": float("nan"),
    }
    tracker = {"as_of": "2026-03-31", "leaderboard": [], "by_fund": {}}
    desk_path = factordata / "smartmoney_desk.json"
    tracker_path = factordata / "smartmoney_tracker.json"
    desk_path.write_text(json.dumps(original_desk, separators=(",", ":")))
    tracker_bytes = json.dumps(tracker, separators=(",", ":")).encode()
    tracker_path.write_bytes(tracker_bytes)
    summary_path = factordata / "institutional_census_summary.json"
    original_summary_bytes = b'{"sentinel":"stale-summary"}'
    summary_path.write_bytes(original_summary_bytes)

    untouched = {
        factordata / "smartmoney.json": b'{"sentinel":"aggregate"}',
        funddata / "fixture.json": b'{"sentinel":"dossier-data"}',
        tmp_path / "site" / "fund_fixture.html": b"dossier-page-sentinel",
        tmp_path / "site" / "data_base.js": b"existing-shim-sentinel",
    }
    for path, payload in untouched.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    monkeypatch.setattr(desk_builder.config, "ROOT", tmp_path)
    monkeypatch.setattr(
        desk_builder.config,
        "load",
        lambda: (_ for _ in ()).throw(AssertionError("render-only must not load collectors")),
    )

    assert desk_builder.render_institutional_census_only() == 0

    rendered_desk = json.loads(desk_path.read_text())
    assert math.isnan(rendered_desk.pop("legacy_nan"))
    expected_unchanged = dict(original_desk)
    expected_unchanged.pop("legacy_nan")
    expected_unchanged.pop("institutional_census")
    observed_unchanged = dict(rendered_desk)
    observed_unchanged.pop("institutional_census")
    assert observed_unchanged == expected_unchanged
    assert rendered_desk["institutional_census"]["leaders"]["broadening"][0][
        "ticker"
    ] == "B0"
    rendered_summary = json.loads(summary_path.read_text())
    assert rendered_summary == rendered_desk["institutional_census"]
    assert summary_path.read_bytes() != original_summary_bytes
    assert tracker_path.read_bytes() == tracker_bytes
    assert all(path.read_bytes() == payload for path, payload in untouched.items())
    html = (tmp_path / "site" / "smart_money.html").read_text()
    assert "B0" in html
    assert "<strong>OLD</strong>" not in html
    css_assets = list((tmp_path / "site" / "assets" / "css").glob("*.css"))
    assert len(css_assets) == 1
    assert css_assets[0].stat().st_size > 1024
    assert f"assets/css/{css_assets[0].name}?v={css_assets[0].stem}" in html
    census_html = html.split('id="sec-census"', 1)[1].split("</section>", 1)[0]
    assert all(line == line.rstrip() for line in census_html.splitlines())


def test_census_template_is_permanent_bilingual_semantic_and_bounded():
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    html = env.get_template("smart_money.html.j2").render(
        desk={"institutional_census": _census_payload()},
        trk={},
        generated_utc="2026-08-08 20:00 UTC",
        active_section="us",
        active_page="smart_money",
    )

    nav_at = html.index('<nav class="sm-rail"')
    census_at = html.index('<section class="institutional-census" id="sec-census"')
    follow_at = html.index('<div class="sm-sec" id="sec-follow"')
    assert nav_at < census_at < follow_at
    assert 'aria-labelledby="census-title"' in html
    assert '<h2 id="census-title">' in html
    assert '<progress class="census-progress" max="100"' in html
    assert "<ol" in html
    assert "ALL SEC 13F FILERS" in html
    assert "SEC 13F披露全景" in html
    assert "Counts are by filer until parent and affiliate normalization is ready." in html
    assert "B5" in html and "B6" not in html
    assert "N5" in html and "N6" not in html
    assert "Sector 5" in html and "Sector 6" not in html
    assert "validated" not in html.casefold()
    assert "flex-wrap:nowrap" in html
    assert ".census-extra > summary { display:flex" in html


def test_smart_money_light_mode_has_page_scoped_depth_and_semantic_inks():
    source = (ROOT / "templates" / "smart_money.html.j2").read_text()
    light_css = source.split(
        "/* ---- light mode: deliberate depth, not a dark-palette inversion ----", 1
    )[1].split("{% endblock %}", 1)[0]

    assert 'html[data-theme="light"] body' in light_css
    assert 'html[data-theme="light"] .sm {' in light_css
    assert "--sm-edge:" in light_css
    assert "--sm-rule:" in light_css
    assert "--sm-shadow:" in light_css
    assert 'html[data-theme="light"] .sm-deck' in light_css
    assert 'html[data-theme="light"] .filing-live' in light_css
    assert 'html[data-theme="light"] .institutional-census' in light_css
    assert 'html[data-theme="light"] .sm-rail' in light_css
    assert "backdrop-filter:blur(14px)" in light_css
    assert "var(--ink-up,var(--up))" in light_css
    assert "var(--ink-down,var(--down))" in light_css
    assert "var(--ink-ok,var(--ok))" in light_css
    assert "var(--ink-act,var(--act))" in light_css
    assert "var(--ink-info,var(--info))" in light_css
    assert ".cap-chip.small { color:var(--ink-ok,var(--ok)); }" in light_css
    assert '.t-red { color:var(--ink-act,var(--act)); }' in light_css
    assert ".chip-fresh.t-green { background:color-mix(in srgb,var(--ok) 8%,#fff); }" in light_css
    assert ".chip-fresh.t-red { background:color-mix(in srgb,var(--act) 7%,#fff); }" in light_css
    assert "outline:2px solid var(--ink-info,var(--info));" in light_css
    assert 'html[data-theme="dark"]' not in light_css

    theme_css = (ROOT / "templates" / "theme.css").read_text()
    light_zh_blocks = [
        block.split("}", 1)[0]
        for block in theme_css.split('html[data-theme="light"][data-lang="zh"] {')[
            1:
        ]
    ]
    light_zh = next(block for block in light_zh_blocks if "--ink-mix-up:" in block)
    assert "--ink-mix-up:" in light_zh and "--ink-mix-down:" in light_zh
    assert "--ink-mix-ok:" not in light_zh and "--ink-mix-act:" not in light_zh


def test_census_template_degraded_state_hides_stale_rankings():
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    degraded = desk_builder._degraded_census("source_rejected")
    degraded["leaders"]["broadening"] = [{"ticker": "STALE"}]
    html = env.get_template("smart_money.html.j2").render(
        desk={"institutional_census": degraded}, trk={},
        generated_utc="2026-08-08 20:00 UTC",
        active_section="us", active_page="smart_money",
    )
    assert "Census refresh pending" in html
    assert "STALE" not in html
    assert '<div class="census-empty" role="status">' in html


def test_build_site_standalone_uses_canonical_cohort_and_writes_json(tmp_path, monkeypatch):
    from engine import smart_money as smart_money_engine

    sm_cfg = {"funds": {"early": {}, "steady": {}}}
    captured: dict = {}

    monkeypatch.setattr(
        build_site,
        "_resolve_smartmoney_canonical_cohort",
        lambda: (sm_cfg, "2026-03-31", ["early", "steady"]),
    )

    def fake_compute(cfg, *, target_period, included_slugs):
        captured.update(cfg=cfg, period=target_period, slugs=list(included_slugs))
        return {
            "as_of": target_period,
            "n_funds": len(included_slugs),
            "n_names": 0,
            "funds": {slug: {"period_end": target_period} for slug in included_slugs},
            "by_ticker": {},
        }

    monkeypatch.setattr(smart_money_engine, "compute_smart_money", fake_compute)
    monkeypatch.setattr(smart_money_engine, "enrich_since_filing", lambda _rows: None)

    out = build_site.build_smartmoney_data(tmp_path)
    written = json.loads((tmp_path / "factordata" / "smartmoney.json").read_text())

    assert captured == {
        "cfg": sm_cfg,
        "period": "2026-03-31",
        "slugs": ["early", "steady"],
    }
    assert out == written
    assert {row["period_end"] for row in written["funds"].values()} == {"2026-03-31"}


def test_build_site_resolves_the_filing_transition_contract(monkeypatch):
    from engine import filing_transition, ownership_event_wire

    funds = {"early": {"name": "Early"}, "steady": {"name": "Steady"}}
    sm_cfg = {"funds": funds}
    observed: dict = {}

    monkeypatch.setattr(build_site.config, "load", lambda: {"smart_money": sm_cfg})

    def fake_latest(roster):
        observed["latest_roster"] = roster
        return {"early": {}}

    monkeypatch.setattr(ownership_event_wire, "latest_fund_filings", fake_latest)

    def fake_clock(roster, *, fund_filings):
        observed.update(clock_roster=roster, filings=fund_filings)
        return {"quarter_end": "2026-06-30"}

    def fake_transition(roster, clock, tracker):
        observed.update(transition_roster=roster, clock=clock, tracker=tracker)
        return {
            "canonical_period": "2026-03-31",
            "canonical_slugs": ["early", "steady"],
        }

    monkeypatch.setattr(ownership_event_wire, "filing_season_clock", fake_clock)
    monkeypatch.setattr(filing_transition, "build_filing_transition", fake_transition)

    resolved_cfg, period, slugs = build_site._resolve_smartmoney_canonical_cohort()

    assert resolved_cfg is sm_cfg
    assert period == "2026-03-31"
    assert slugs == ["early", "steady"]
    assert observed["clock_roster"] is funds
    assert observed["transition_roster"] is funds
    assert observed["tracker"] == {}
