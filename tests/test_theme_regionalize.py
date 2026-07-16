"""Regionalization of the theme engine (theme_scoring / basket_score / theme_alerts).

Verify the per-region data plumbing routes correctly (US unchanged; CN/HK/CA get their own
paths/breadth), theme_alerts is region-scoped (no cross-market collision), and the full
compute_theme_intel runs for every market when caches are present. No network.
"""
from __future__ import annotations

from engine import basket_score, theme_alerts


def test_theme_alerts_paths_are_region_scoped():
    assert theme_alerts._path("us").as_posix().endswith("data/themes/alerts.jsonl")
    assert theme_alerts._path("china").as_posix().endswith("data/themes_china/alerts.jsonl")
    assert theme_alerts._state_path("hk").as_posix().endswith("data/themes_hk/state.json")
    # distinct dirs → no cross-market alert collision
    assert theme_alerts._path("china") != theme_alerts._path("hk") != theme_alerts._path("canada")


def test_market_concentration_region_dirs():
    assert basket_score._BREADTH_DIR["us"] == "breadth"
    assert basket_score._BREADTH_DIR["china"] == "china_breadth"
    assert basket_score._BREADTH_DIR["hk"] == "hk_breadth"
    assert basket_score._BREADTH_DIR["canada"] == "canada_breadth"


def test_theme_alerts_region_roundtrip(tmp_path, monkeypatch):
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    intel = {"as_of": "2026-06-19", "themes": [
        {"id": "cn_semis", "label": "neutral", "reco": "hold", "rank": 1, "name": "Semis", "name_zh": "半导体", "score": 50}]}
    # seed china silently; us stays empty (region isolation)
    assert theme_alerts.rebuild(intel, "china") == []
    assert (tmp_path / "themes_china" / "state.json").exists()
    assert not (tmp_path / "themes" / "state.json").exists()
    intel2 = {"as_of": "2026-06-20", "themes": [
        {"id": "cn_semis", "label": "emerging", "reco": "enter", "rank": 1, "name": "Semis", "name_zh": "半导体", "score": 60}]}
    fired = theme_alerts.rebuild(intel2, "china")
    assert fired and theme_alerts.load_events("us") == []   # us feed untouched


def test_compute_theme_intel_all_regions_when_present(tmp_path, monkeypatch):
    from engine.theme_scoring import compute_theme_intel
    from engine import basket_breadth_divergence as bd

    # compute_theme_intel stamps elevated/high breadth-divergence textures into
    # the forward accountability log as a side effect — redirect the stamp to
    # tmp so real caches are read but data/breadth_divergence/ is never written.
    monkeypatch.setattr(bd, "_log_path", lambda: tmp_path / "forward_log.parquet")
    for region in ("us", "china", "hk", "canada"):
        ti = compute_theme_intel(region)
        if ti is None:            # caches absent in a CI shard
            continue
        assert ti["n_themes"] >= 1
        assert "act_now" in ti and "market_concentration" in ti
        t = ti["themes"][0]
        assert set(t["textures"]) == {"bull_age", "overbought", "clean_entry", "rollover_risk",
                                      "breadth_divergence"}
