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
        # ALL-of (MAJOR-1 fix): energy's price cell names oil/gas/fuels across
        # 4 tickers, so a "covered" fixture must create every one of them, not
        # a single stand-in.
        for tk in ("CL_F", "NG_F", "HO_F", "RB_F"):
            (root / "data" / "yahoo" / f"{tk}.parquet").write_bytes(b"x")
        (root / "data" / "yahoo" / "GC_F.parquet").write_bytes(b"x")
        (root / "data" / "yahoo" / "HG_F.parquet").write_bytes(b"x")
        (root / "data" / "yahoo" / "ZC_F.parquet").write_bytes(b"x")
    if energy_supply_artifacts:
        for f in ("crude_stocks", "crude_production", "crude_imports"):
            (root / "data" / "eia" / f"{f}.parquet").write_bytes(b"x")
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


def test_9_multi_commodity_claims_are_backed_by_one_artifact_per_named_commodity():
    """B3 review MAJOR-5: a family whose cell copy names N commodities must
    check N filesystem artifacts — one ticker standing proxy for every named
    commodity is exactly the overclaim the review measured (e.g. "precious"
    printed gold/silver/platinum/palladium on GC_F.parquet alone)."""
    by_id = {f["id"]: f for f in FAMILIES}
    assert len(by_id["energy"]["price"]["artifacts"]) >= 3    # oil, gas, fuels
    assert len(by_id["precious"]["price"]["artifacts"]) == 4  # gold/silver/platinum/palladium
    assert len(by_id["agri"]["price"]["artifacts"]) == 8      # corn..cotton
    for fam_id in ("energy", "precious", "agri"):
        artifacts = by_id[fam_id]["price"]["artifacts"]
        assert len(set(artifacts)) == len(artifacts), "no duplicate tickers"
        for artifact in artifacts:
            assert artifact.startswith("data/yahoo/") and artifact.endswith(".parquet")


def test_10_partial_artifact_set_never_claims_full_multi_commodity_coverage(tmp_path):
    """B3 round-2 review MAJOR-1: `_axis_cell` was ANY-of over `artifacts`, so
    with only `data/yahoo/GC_F.parquet` on disk the precious row still reported
    state 'partial'/'covered'-shaped copy naming gold/silver/platinum/palladium
    (measured live). The check must be ALL-of: every ticker the cell text names
    has to actually exist before that text is shown as a 'read' claim."""
    root = tmp_path
    (root / "engine").mkdir(parents=True, exist_ok=True)
    (root / "data" / "yahoo").mkdir(parents=True, exist_ok=True)
    (root / "engine" / "commodity_inputs.py").write_text("# fake\n")
    # Only ONE of the four precious-metal tickers on disk. precious has no
    # supply axis (FAMILIES[1]["supply"] is None), so "covered" (price+supply)
    # is never reachable for this family — the axis under test is the PRICE
    # cell's own read/not-read claim, not the row's overall state.
    (root / "data" / "yahoo" / "GC_F.parquet").write_bytes(b"x")

    rows = compute_coverage_matrix(root=root)["rows"]
    precious = next(r for r in rows if r["id"] == "precious")
    assert precious["price_en"] != "Daily prices for gold, silver, platinum and palladium"
    assert not precious["sources"], "a partial artifact set must not cite itself as a read source"

    # Now complete the set: all four exist -> the full claim is finally honest.
    for tk in ("SI_F", "PL_F", "PA_F"):
        (root / "data" / "yahoo" / f"{tk}.parquet").write_bytes(b"x")
    rows2 = compute_coverage_matrix(root=root)["rows"]
    precious2 = next(r for r in rows2 if r["id"] == "precious")
    assert precious2["state"] == "partial"  # "prices only" — precious has no supply axis
    assert precious2["price_en"] == "Daily prices for gold, silver, platinum and palladium"
    assert precious2["sources"], "a complete artifact set must now cite its source"
