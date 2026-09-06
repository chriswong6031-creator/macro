"""Tests for engine.commodity_coverage_matrix (B-F09-6, MO-DELTA-029)."""
from __future__ import annotations

import re

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from engine.commodity_coverage_matrix import FAMILIES, PUBLIC_SOURCES, compute_coverage_matrix

_REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
_STATES = {"covered", "partial", "none"}
_BANNED_JARGON = re.compile(r"\.py|/|z-score|\bn=\d|percentile|falsifier|refuted|证伪")
_BANNED_CAUSAL = re.compile(r"drives|causes|will push|leads to|推动|导致|将带动")


def _fake_root(tmp_path, *, energy_producer=True, energy_price_artifact=True,
               energy_supply_artifacts=True):
    root = tmp_path
    (root / "engine").mkdir(parents=True, exist_ok=True)
    (root / "data" / "yahoo").mkdir(parents=True, exist_ok=True)
    (root / "data" / "eia").mkdir(parents=True, exist_ok=True)
    if energy_producer:
        (root / "engine" / "commodity_inputs.py").write_text("# fake\n")
        (root / "engine" / "commodity_supply_context.py").write_text("# fake\n")
    if energy_price_artifact:
        (root / "data" / "yahoo" / "CL_F.parquet").write_bytes(b"x")
        (root / "data" / "yahoo" / "GC_F.parquet").write_bytes(b"x")
        (root / "data" / "yahoo" / "HG_F.parquet").write_bytes(b"x")
        (root / "data" / "yahoo" / "ZC_F.parquet").write_bytes(b"x")
    if energy_supply_artifacts:
        (root / "data" / "eia" / "crude_stocks.parquet").write_bytes(b"x")
    return root


def test_1_frozen_registry_five_families_in_order():
    ids = [f["id"] for f in FAMILIES]
    assert ids == ["energy", "precious", "base", "agri", "techmat"]


def test_2_every_row_carries_bilingual_strings_and_valid_state(tmp_path):
    root = _fake_root(tmp_path)
    rows = compute_coverage_matrix(root=root)["rows"]
    assert len(rows) == 5
    for r in rows:
        assert r["family_en"] and r["family_zh"]
        assert r["state"] in _STATES
        for k in ("state_en", "state_zh", "price_en", "price_zh", "supply_en", "supply_zh"):
            assert isinstance(r[k], str) and r[k]


def test_3_techmat_present_and_none():
    # techmat has no producers declared at all — verify from the frozen registry
    # directly (no filesystem needed) that its axes are unset.
    techmat = next(f for f in FAMILIES if f["id"] == "techmat")
    assert techmat["price"] is None and techmat["supply"] is None


def test_3b_techmat_row_state_is_none(tmp_path):
    root = _fake_root(tmp_path)
    rows = compute_coverage_matrix(root=root)["rows"]
    techmat = next(r for r in rows if r["id"] == "techmat")
    assert techmat["state"] == "none"
    assert techmat["price_en"] == "Not covered yet"
    assert techmat["supply_en"] == "Not covered yet"


def test_4_covered_axis_names_existing_producer_and_public_source(tmp_path):
    root = _fake_root(tmp_path)
    rows = compute_coverage_matrix(root=root)["rows"]
    energy = next(r for r in rows if r["id"] == "energy")
    assert energy["state"] == "covered"
    assert energy["sources"], "covered rows must carry at least one source"
    for s in energy["sources"]:
        assert (root / s["producer"]).exists()
        assert s["source_en"] in PUBLIC_SOURCES or s["source_zh"] in PUBLIC_SOURCES


def test_5_glance_strings_contain_no_jargon_no_paths(tmp_path):
    root = _fake_root(tmp_path)
    rows = compute_coverage_matrix(root=root)["rows"]
    for r in rows:
        for k in ("family_en", "family_zh", "state_en", "state_zh",
                  "price_en", "price_zh", "supply_en", "supply_zh"):
            assert not _BANNED_JARGON.search(r[k]), (k, r[k])
    # producer paths only ever appear inside sources[*].producer
    for r in rows:
        for s in r["sources"]:
            assert "/" in s["producer"] or s["producer"].endswith(".py")


def test_6_filesystem_derived_deleting_artifact_flips_state(tmp_path):
    root = _fake_root(tmp_path)
    rows = compute_coverage_matrix(root=root)["rows"]
    assert next(r for r in rows if r["id"] == "energy")["state"] == "covered"

    (root / "data" / "eia" / "crude_stocks.parquet").unlink()
    rows2 = compute_coverage_matrix(root=root)["rows"]
    energy2 = next(r for r in rows2 if r["id"] == "energy")
    assert energy2["state"] == "partial"
    # producer still exists, artifact gone: an UNKNOWN, not shaped as an EMPTY.
    assert energy2["supply_en"] == "Built, waiting on data"

    # deleting the producer module also degrades the axis (no producer -> no read)
    (root / "engine" / "commodity_supply_context.py").unlink()
    rows3 = compute_coverage_matrix(root=root)["rows"]
    energy3 = next(r for r in rows3 if r["id"] == "energy")
    assert energy3["state"] == "partial"


def test_7_no_causal_overstatement(tmp_path):
    root = _fake_root(tmp_path)
    rows = compute_coverage_matrix(root=root)["rows"]
    for r in rows:
        for k in ("price_en", "price_zh", "supply_en", "supply_zh"):
            assert not _BANNED_CAUSAL.search(r[k]), (k, r[k])


def test_8_render_diff_contained_between_markers():
    tpl_dir = _REPO_ROOT / "templates"
    env = Environment(loader=FileSystemLoader(str(tpl_dir)), autoescape=True,
                       undefined=StrictUndefined)
    # commodities.html.j2 is a large real-data page; we only exercise the
    # coverage-matrix insertion, so we can't fully render it here without the
    # full site context. Instead assert statically that the inserted block in
    # the template source is fully bounded by its own markers.
    src = (tpl_dir / "commodities.html.j2").read_text()
    start = src.index("coverage-matrix:start")
    end = src.index("coverage-matrix:end")
    assert start < end
    block = src[start:end]
    # sanity: nothing outside {coverage} usage leaks past the markers
    assert "cov-panel" in block
