"""Cross-market narrative cross-reference — gates + structure (display-only).

Pure-function tests over a synthetic site/ tree (no real caches needed): the canon crosswalk,
the region-specificity exclusion, the macro-regime-alignment flag, the China↔HK co-listing flag,
and the 'hotter elsewhere' suppression under regime divergence.
"""
from __future__ import annotations

import json

from engine import narrative_crossmarket as xm


def _write_market(site, data_dir, region, themes, quad=None):
    d = site / xm._BASKETS_DATA[region]
    d.mkdir(parents=True, exist_ok=True)
    (d / "baskets.json").write_text(json.dumps({"theme_intel": {"as_of": "2026-06-19", "themes": themes}}))
    if quad is not None:
        rd = data_dir / ("regime" if region == "us" else f"{region}_regime")
        rd.mkdir(parents=True, exist_ok=True)
        (rd / "latest.json").write_text(json.dumps({"quad": quad}))


def _theme(bid, name, score, label="neutral", accel=0.0, rel=0.0):
    return {"id": bid, "name": name, "name_zh": name, "score": score, "label": label,
            "reco": "hold", "accel_z": accel, "perf": {"20d": {"rel": rel}}}


def _setup(tmp_path, monkeypatch):
    site = tmp_path / "site"
    data = tmp_path / "data"
    monkeypatch.setattr(xm.config, "data_dir", lambda: data)
    # US (Q1) and China (Q3) both run semis; canada (Q1) runs gold; HK runs autos (co-listed w/ china)
    _write_market(site, data, "us", [_theme("ai_semiconductors", "US Semis", 80, "dominant", 1.0)], quad="Q1")
    _write_market(site, data, "china", [_theme("cn_semis", "CN Semis", 55, "neutral"),
                                        _theme("cn_autos", "CN Autos", 60, "emerging", 1.0)], quad="Q3")
    _write_market(site, data, "hk", [_theme("hk_ev", "HK EV", 50, "neutral")], quad="Q2")
    _write_market(site, data, "canada", [_theme("ca_gold", "CA Gold", 70, "dominant")], quad="Q1")
    return site


def test_region_specificity_excludes_domestic_themes(tmp_path, monkeypatch):
    site = _setup(tmp_path, monkeypatch)
    cm = xm.compute_crossmarket(site)
    # banks / housing / utilities etc. are NOT in the canon → never get a chip
    domestic = {"regional_banks", "cn_banks", "hk_banks", "ca_banks", "housing", "ca_reits", "hk_gaming"}
    for region, themes in cm["links"].items():
        assert not (set(themes) & domestic), f"{region} leaked a domestic theme into the crosswalk"


def test_regime_caveat_flags_divergent_macro(tmp_path, monkeypatch):
    site = _setup(tmp_path, monkeypatch)
    cm = xm.compute_crossmarket(site)
    # China(Q3) ↔ US(Q1) semis cross-ref must carry the regime caveat
    cn = cm["links"]["china"]["cn_semis"]
    us_ref = next(o for o in cn["others"] if o["region"] == "us")
    assert us_ref["regime_caveat"] is True
    assert us_ref["co_listed"] is False


def test_co_listing_flags_china_hk(tmp_path, monkeypatch):
    site = _setup(tmp_path, monkeypatch)
    cm = xm.compute_crossmarket(site)
    cn = cm["links"]["china"]["cn_autos"]
    hk_ref = next(o for o in cn["others"] if o["region"] == "hk")
    assert hk_ref["co_listed"] is True


def test_hotter_elsewhere_suppressed_under_regime_divergence(tmp_path, monkeypatch):
    site = _setup(tmp_path, monkeypatch)
    cm = xm.compute_crossmarket(site)
    # CN Semis (55) vs US Semis (80, dominant) — would be "hotter", but US is in a DIFFERENT regime
    # (Q1 vs Q3) so it must NOT be claimed as a clean early-detection.
    cn = cm["links"]["china"]["cn_semis"]
    assert "us" not in cn["hotter_elsewhere"]


def test_disclaimer_and_quads_present(tmp_path, monkeypatch):
    site = _setup(tmp_path, monkeypatch)
    cm = xm.compute_crossmarket(site)
    assert "NOT a validated signal" in cm["disclaimer"]["en"]
    assert cm["quads"]["us"] == "Q1" and cm["quads"]["china"] == "Q3"
    assert cm["quads"]["intl"] is None                      # intl has no single regime
