"""tests/test_sanctions_map_engine.py — packet A-F02-1 §9.1."""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import yaml

from engine import sanctions_map
from engine.sanctions_map import rungs_for, split_program_field


def _sdn_csv(codes: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    for i, code in enumerate(codes):
        row = [""] * 8
        row[0] = str(i)
        row[3] = code
        w.writerow(row)
    return buf.getvalue()


def _config(rows: list[dict], thematic: list[dict] | None = None) -> str:
    payload: dict = {"programs": rows}
    if thematic is not None:
        payload["thematic"] = thematic
    return yaml.safe_dump(payload)


def test_build_never_raises_on_missing_store(tmp_path):
    vm = sanctions_map.build(
        sdn_file=tmp_path / "missing.csv",
        meta_file=tmp_path / "missing.json",
        programs_config=tmp_path / "missing.yml",
    )
    assert vm["as_of"] is None
    assert vm["countries"] == []
    assert vm["unresolved"] == []
    assert vm["coverage"] is None


def test_country_with_no_programmes_is_absent_never_zero(tmp_path):
    sdn = tmp_path / "sdn.csv"
    sdn.write_text(_sdn_csv(["RUSSIA-EO14024"]), encoding="utf-8")
    cfg = tmp_path / "cfg.yml"
    cfg.write_text(_config([
        {"code": "RUSSIA-EO14024", "iso3": "RUS",
         "country_name_en": "Russia", "country_name_zh": "俄罗斯",
         "name_en": "Russia — EO 14024", "name_zh": "俄罗斯 — 第14024号行政命令"},
    ]), encoding="utf-8")
    vm = sanctions_map.build(sdn_file=sdn, meta_file=tmp_path / "meta.json", programs_config=cfg)
    isos = [c["iso3"] for c in vm["countries"]]
    assert "USA" not in isos
    for c in vm["countries"]:
        assert c["n_programs"] > 0


def test_unresolved_code_is_counted_never_dropped(tmp_path):
    sdn = tmp_path / "sdn.csv"
    sdn.write_text(_sdn_csv(["RUSSIA-EO14024", "UNKNOWN-CODE"]), encoding="utf-8")
    cfg = tmp_path / "cfg.yml"
    cfg.write_text(_config([
        {"code": "RUSSIA-EO14024", "iso3": "RUS",
         "country_name_en": "Russia", "country_name_zh": "俄罗斯",
         "name_en": "Russia — EO 14024", "name_zh": "俄罗斯 — 第14024号行政命令"},
    ]), encoding="utf-8")
    vm = sanctions_map.build(sdn_file=sdn, meta_file=tmp_path / "meta.json", programs_config=cfg)
    codes = [u["code"] for u in vm["unresolved"]]
    assert "UNKNOWN-CODE" in codes
    assert vm["coverage"]["resolved"] + vm["coverage"]["unresolved"] + vm["coverage"]["thematic"] == vm["n_programs_total"]


def test_thematic_codes_do_not_count_as_unresolved(tmp_path):
    sdn = tmp_path / "sdn.csv"
    sdn.write_text(_sdn_csv(["RUSSIA-EO14024", "SDGT"]), encoding="utf-8")
    cfg = tmp_path / "cfg.yml"
    cfg.write_text(_config(
        [{"code": "RUSSIA-EO14024", "iso3": "RUS",
          "country_name_en": "Russia", "country_name_zh": "俄罗斯",
          "name_en": "Russia — EO 14024", "name_zh": "俄罗斯 — 第14024号行政命令"}],
        thematic=[{"code": "SDGT", "name_en": "Global Terrorism", "name_zh": "全球恐怖主义"}],
    ), encoding="utf-8")
    vm = sanctions_map.build(sdn_file=sdn, meta_file=tmp_path / "meta.json", programs_config=cfg)
    assert vm["coverage"]["thematic"] == 1
    assert vm["coverage"]["unresolved"] == 0
    assert vm["coverage"]["resolved"] == 1
    assert [t["code"] for t in vm["thematic"]] == ["SDGT"]


def test_multiple_codes_same_country_raise_rung(tmp_path):
    sdn = tmp_path / "sdn.csv"
    sdn.write_text(_sdn_csv(["A", "B", "C", "D"]), encoding="utf-8")
    cfg = tmp_path / "cfg.yml"
    rows = [
        {"code": c, "iso3": "RUS", "country_name_en": "Russia", "country_name_zh": "俄罗斯",
         "name_en": f"Russia — {c}", "name_zh": f"俄罗斯 — {c}"}
        for c in ("A", "B", "C", "D")
    ]
    cfg.write_text(_config(rows), encoding="utf-8")
    vm = sanctions_map.build(sdn_file=sdn, meta_file=tmp_path / "meta.json", programs_config=cfg)
    assert len(vm["countries"]) == 1
    assert vm["countries"][0]["n_programs"] == 4
    assert vm["countries"][0]["rung"] == 3
    assert vm["n_countries"] == 1


def test_coverage_sums_to_total_one_integer_law(tmp_path):
    sdn = tmp_path / "sdn.csv"
    sdn.write_text(_sdn_csv(["A", "B", "C"]), encoding="utf-8")
    cfg = tmp_path / "cfg.yml"
    cfg.write_text(_config(
        [{"code": "A", "iso3": "RUS", "country_name_en": "Russia", "country_name_zh": "俄罗斯",
          "name_en": "Russia", "name_zh": "俄罗斯"}],
        thematic=[{"code": "B"}],
    ), encoding="utf-8")
    vm = sanctions_map.build(sdn_file=sdn, meta_file=tmp_path / "meta.json", programs_config=cfg)
    assert vm["n_programs_total"] == 3
    assert vm["coverage"]["resolved"] + vm["coverage"]["unresolved"] + vm["coverage"]["thematic"] == 3


def test_rung_boundaries_exact():
    assert sanctions_map._rung(1) == 1
    assert sanctions_map._rung(2) == 2
    assert sanctions_map._rung(3) == 2
    assert sanctions_map._rung(4) == 3


def test_rungs_for_marks_unknown_when_coverage_incomplete():
    vm = {
        "countries": [{"iso3": "RUS", "rung": 3}],
        "coverage": {"resolved": 1, "unresolved": 2, "thematic": 0},
    }
    rungs = rungs_for(vm, {"RUS", "CHN", "IRN"})
    assert rungs["RUS"] == 3
    assert rungs["CHN"] == "x"
    assert rungs["IRN"] == "x"


def test_rungs_for_not_named_when_coverage_complete():
    vm = {
        "countries": [{"iso3": "RUS", "rung": 3}],
        "coverage": {"resolved": 1, "unresolved": 0, "thematic": 5},
    }
    rungs = rungs_for(vm, {"RUS", "CHN"})
    assert rungs["RUS"] == 3
    assert rungs["CHN"] == 0


def test_as_of_falls_back_to_fetched_at_date(tmp_path):
    sdn = tmp_path / "sdn.csv"
    sdn.write_text(_sdn_csv(["A"]), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({
        "source_url": "https://example.test/sdn.csv",
        "list_published_date": None,
        "fetched_at": "2026-09-06T05:53:36Z",
    }), encoding="utf-8")
    cfg = tmp_path / "cfg.yml"
    cfg.write_text(_config([
        {"code": "A", "iso3": "RUS", "country_name_en": "Russia", "country_name_zh": "俄罗斯",
         "name_en": "Russia", "name_zh": "俄罗斯"},
    ]), encoding="utf-8")
    vm = sanctions_map.build(sdn_file=sdn, meta_file=meta, programs_config=cfg)
    assert vm["as_of"] == "2026-09-06"


def test_split_program_field_whitespace_variants():
    assert split_program_field("[A] [B]") == ["A", "B"]
    assert split_program_field("[A]  [B]") == ["A", "B"]
    assert split_program_field("[A]\t[B]") == ["A", "B"]
    assert split_program_field("A") == ["A"]
    assert split_program_field("-0-") == []


def test_config_iso3_subset_of_worldmap_no_parallel_country_master():
    """MINOR 7 / acceptance 3: geometry identity lives on the Natural Earth
    worldmap partial — not a decorative SHARED_ISO3_KEYS alias of intl_risk.
    Every config country must have a map path (same guard as
    tests/test_worldmap_base.py::test_iso3_superset_of_config_countries)."""
    assert not hasattr(sanctions_map, "SHARED_ISO3_KEYS")

    map_html = (Path("templates/_worldmap_base.html.j2").read_text(encoding="utf-8"))
    map_iso3 = set(re.findall(r'data-iso3="([A-Z]{3})"', map_html))
    cfg = yaml.safe_load(Path("config/sanctions_ofac_programs.yml").read_text(encoding="utf-8"))
    cfg_iso3 = {
        str(row["iso3"]).upper()
        for row in (cfg.get("programs") or [])
        if row.get("iso3")
    }
    missing = sorted(cfg_iso3 - map_iso3)
    assert missing == [], f"config iso3 missing from worldmap: {missing}"
