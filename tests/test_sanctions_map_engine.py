"""tests/test_sanctions_map_engine.py — packet A-F02-1 §9.1."""
from __future__ import annotations

import csv
import io
import json

import yaml

from engine import sanctions_map


def _sdn_csv(codes: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    for i, code in enumerate(codes):
        row = [""] * 8
        row[0] = str(i)
        row[3] = code
        w.writerow(row)
    return buf.getvalue()


def _config(rows: list[dict]) -> str:
    return yaml.safe_dump({"programs": rows})


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
        {"code": "RUSSIA-EO14024", "iso3": "RUS", "name_en": "Russia", "name_zh": "俄罗斯"},
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
        {"code": "RUSSIA-EO14024", "iso3": "RUS", "name_en": "Russia", "name_zh": "俄罗斯"},
    ]), encoding="utf-8")
    vm = sanctions_map.build(sdn_file=sdn, meta_file=tmp_path / "meta.json", programs_config=cfg)
    codes = [u["code"] for u in vm["unresolved"]]
    assert "UNKNOWN-CODE" in codes
    assert vm["coverage"]["resolved"] + vm["coverage"]["unresolved"] == vm["n_programs_total"]


def test_coverage_sums_to_total_one_integer_law(tmp_path):
    sdn = tmp_path / "sdn.csv"
    sdn.write_text(_sdn_csv(["A", "B", "C"]), encoding="utf-8")
    cfg = tmp_path / "cfg.yml"
    cfg.write_text(_config([{"code": "A", "iso3": "RUS", "name_en": "Russia", "name_zh": "俄罗斯"}]),
                    encoding="utf-8")
    vm = sanctions_map.build(sdn_file=sdn, meta_file=tmp_path / "meta.json", programs_config=cfg)
    assert vm["n_programs_total"] == 3
    assert vm["coverage"]["resolved"] + vm["coverage"]["unresolved"] == 3


def test_rung_boundaries_exact():
    assert sanctions_map._rung(1) == 1
    assert sanctions_map._rung(2) == 2
    assert sanctions_map._rung(3) == 2
    assert sanctions_map._rung(4) == 3
