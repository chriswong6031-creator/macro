"""The factors-page IC panel loader (scripts.build_site._load_ic_scorecard).

Surfaces the leak-free point-in-time IC scorecard (data/edgar/ic_scorecard.json,
written by scripts.factor_ic_scorecard) onto factors.html. The loader must:
sort factors by forward IC-IR (best first), tag whether ANY clears BH-FDR, and
degrade-never-raise when the file is missing/garbage (so the panel just hides).
"""
from __future__ import annotations

import json

from lib import config
from scripts import build_site


def _scorecard():
    return {
        "horizon_d": 63, "rebalances": 11, "span": "2023-06-30..2025-12-31",
        "median_universe": 1323, "leak_free": True,
        "factors": {
            "value": {"mean_ic": 0.028, "ic_ir_ann": 0.64, "t_hac": 1.16, "hit": 0.73,
                      "q_fdr": 0.54, "n": 11, "survives_fdr": False},
            "payout": {"mean_ic": 0.023, "ic_ir_ann": 0.82, "t_hac": 1.60, "hit": 0.64,
                       "q_fdr": 0.32, "n": 11, "survives_fdr": False},
            "low_vol": {"mean_ic": 0.008, "ic_ir_ann": 0.07, "t_hac": 0.15, "hit": 0.56,
                        "q_fdr": 0.93, "n": 9, "survives_fdr": False},
            "quality": {"mean_ic": -0.021, "ic_ir_ann": -0.64, "t_hac": -1.57, "hit": 0.46,
                        "q_fdr": 0.32, "n": 11, "survives_fdr": False},
        },
        "collinearity": {"mean_abs_corr_raw": 0.126, "mean_abs_corr_orth": 0.054,
                         "top_pairs": [{"a": "low_vol", "b": "low_beta", "corr": 0.73}]},
    }


def test_loader_sorts_and_flags(tmp_path, monkeypatch):
    edgar = tmp_path / "edgar"
    edgar.mkdir()
    (edgar / "ic_scorecard.json").write_text(json.dumps(_scorecard()))
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    ic = build_site._load_ic_scorecard()
    assert ic is not None
    # best forward IC-IR first (payout 0.82 > value 0.64 > low_vol 0.07 > quality -0.64)
    assert [r["factor"] for r in ic["rows"]] == ["payout", "value", "low_vol", "quality"]
    # every row carries a display label + its honest per-factor n (low_vol only 9)
    assert all("label_en" in r for r in ic["rows"])
    assert next(r for r in ic["rows"] if r["factor"] == "low_vol")["n"] == 9
    # none survive -> the panel leads with the null headline
    assert ic["any_survive"] is False


def test_loader_degrades_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)   # no edgar/ic_scorecard.json
    assert build_site._load_ic_scorecard() is None


def test_loader_degrades_on_garbage(tmp_path, monkeypatch):
    edgar = tmp_path / "edgar"
    edgar.mkdir()
    (edgar / "ic_scorecard.json").write_text("{not json")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    assert build_site._load_ic_scorecard() is None


def test_loader_empty_factors_hides(tmp_path, monkeypatch):
    edgar = tmp_path / "edgar"
    edgar.mkdir()
    (edgar / "ic_scorecard.json").write_text(json.dumps({"factors": {}}))
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    assert build_site._load_ic_scorecard() is None
