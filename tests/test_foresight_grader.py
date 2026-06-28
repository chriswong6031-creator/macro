"""engine.foresight_grader — the forward-grading learning loop. Verifies a matured PRECIPICE
flag grades HIT when the theme outperformed SPY, a not-yet-matured flag stays pending, and a
GLUT exit call grades HIT on UNDERperformance. Synthetic ledger + price fixtures.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from engine import foresight_grader as gr


def _series(level_end: float):
    idx = pd.date_range("2025-06-01", periods=400, freq="D")
    return pd.Series(np.linspace(100.0, level_end, len(idx)), index=idx)


def _patch(monkeypatch, tmp_path, ledger_rows, closes):
    (tmp_path / "foresight").mkdir(parents=True, exist_ok=True)
    (tmp_path / "foresight" / "log.jsonl").write_text(
        "\n".join(json.dumps(r) for r in ledger_rows))
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(gr.config, "load",
                        lambda: {"themes": {"memory_storage": {"tickers": ["MU", "WDC"]}}})
    monkeypatch.setattr(gr, "_closes", lambda tk: closes.get(tk))


def test_matured_thesis_hits_on_outperformance(monkeypatch, tmp_path):
    closes = {"MU": _series(140), "WDC": _series(135), "SPY": _series(110)}   # theme >> SPY
    _patch(monkeypatch, tmp_path,
           [{"theme": "memory_storage", "asof": "2026-01-01", "stage": "PRECIPICE"}], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    assert s["n_graded"] == 1 and s["n_pending"] == 0
    assert s["by_stage"]["PRECIPICE"]["hits"] == 1
    assert s["by_stage"]["PRECIPICE"]["avg_excess_pct"] > 0


def test_thesis_misses_on_underperformance(monkeypatch, tmp_path):
    closes = {"MU": _series(101), "WDC": _series(100), "SPY": _series(130)}   # theme << SPY
    _patch(monkeypatch, tmp_path,
           [{"theme": "memory_storage", "asof": "2026-01-01", "stage": "BROADENING"}], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    assert s["by_stage"]["BROADENING"]["hits"] == 0


def test_not_yet_matured_is_pending(monkeypatch, tmp_path):
    closes = {"MU": _series(140), "WDC": _series(135), "SPY": _series(110)}
    _patch(monkeypatch, tmp_path,
           [{"theme": "memory_storage", "asof": "2026-05-20", "stage": "PRECIPICE"}], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)   # <90d elapsed
    assert s["n_graded"] == 0 and s["n_pending"] == 1


def test_glut_exit_hits_on_underperformance(monkeypatch, tmp_path):
    (tmp_path / "glut_watch").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glut_watch" / "log.jsonl").write_text(
        json.dumps({"theme": "memory_storage", "asof": "2026-01-01", "band": "GLUT"}))
    closes = {"MU": _series(95), "WDC": _series(90), "SPY": _series(120)}     # theme << SPY -> glut call right
    _patch(monkeypatch, tmp_path, [], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    assert s["by_stage"]["GLUT-EXIT"]["hits"] == 1


# ---- the three PIT-rigor guards ----

def test_survivorship_delisted_member_counted_at_loss(monkeypatch, tmp_path):
    # WDC delists mid-horizon (series ends 2026-02-15, well before end 2026-04-01) at a loss.
    # Survivorship-free: WDC's loss IS counted -> the basket underperforms -> the thesis MISSES.
    # (If WDC were dropped, MU alone would beat SPY and it would falsely register a HIT.)
    didx = pd.date_range("2025-06-01", "2026-02-15", freq="D")
    wdc = pd.Series(np.linspace(100.0, 50.0, len(didx)), index=didx)
    closes = {"MU": _series(140), "WDC": wdc, "SPY": _series(110)}
    _patch(monkeypatch, tmp_path,
           [{"theme": "memory_storage", "asof": "2026-01-01", "stage": "PRECIPICE"}], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    assert s["n_graded"] == 1
    assert s["by_stage"]["PRECIPICE"]["hits"] == 0               # WDC's loss dragged the basket -> miss
    assert s["by_stage"]["PRECIPICE"]["avg_excess_pct"] < 0


def test_point_in_time_membership_from_ledger(monkeypatch, tmp_path):
    # ledger carries the AT-FLAG snapshot [MU, OLD]; config says [MU, WDC]. Grading must use the
    # snapshot. OLD fell, so the basket misses — proving config's later, winning WDC was NOT used.
    closes = {"MU": _series(140), "WDC": _series(150), "OLD": _series(80), "SPY": _series(110)}
    _patch(monkeypatch, tmp_path, [{"theme": "memory_storage", "asof": "2026-01-01",
                                    "stage": "PRECIPICE", "members": ["MU", "OLD"]}], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    assert s["n_graded"] == 1
    assert s["by_stage"]["PRECIPICE"]["hits"] == 0               # used [MU,OLD] (PIT), not config [MU,WDC]


def test_fdr_and_wilson_reported(monkeypatch, tmp_path):
    closes = {"MU": _series(150), "WDC": _series(150), "SPY": _series(105)}
    _patch(monkeypatch, tmp_path,
           [{"theme": "memory_storage", "asof": "2026-01-01", "stage": "PRECIPICE"}], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    assert "pooled_ci95" in s and "n_significant_fdr" in s
    bt = s["by_theme"]["memory_storage"]
    assert bt["p_value"] is not None and bt["ci95"] is not None and "significant_fdr" in bt


def test_stat_helpers_and_delisting_gap():
    assert abs(gr._binom_sf(5, 5) - 0.03125) < 1e-9 and gr._binom_sf(0, 0) == 1.0
    assert gr._wilson(0, 0) is None
    # Benjamini-Yekutieli is conservative vs BH: with m=3, H_m≈1.833, only 'a' clears
    assert gr._fdr_significant({"a": 0.01, "b": 0.04, "c": 0.9}) == {"a"}
    idx = pd.date_range("2026-01-01", "2026-02-01", freq="D")
    s = pd.Series([100.0] * (len(idx) - 5) + [80.0] * 5, index=idx)   # last close 2026-02-01 = 80
    assert abs(gr._ret(s, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01")) + 0.2) < 1e-9  # delisted
    assert gr._ret(s, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-05")) is None            # just lagging


def test_no_lookahead_terminal_window():
    # a name with a data hole straddling `end` that RESUMES months later must NOT use the resume
    # price as terminal (that would import future returns). It's treated as delisted -> last close.
    a = pd.date_range("2025-12-01", "2026-03-01", freq="D")     # last trade 31d before end -> delisted
    b = pd.date_range("2026-05-10", "2026-06-30", freq="D")     # resumes long after end
    s = pd.concat([pd.Series([100.0] * len(a), index=a), pd.Series([200.0] * len(b), index=b)])
    r = gr._ret(s, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01"))
    assert r is not None and abs(r - 0.0) < 1e-9      # terminal = last close 100 (NOT the 200 resume)


def test_dead_name_fallback_counts_bankruptcy_as_total_loss(monkeypatch, tmp_path):
    (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": ["DEAD", "DEAD"], "date": ["2026-01-01", "2026-02-01"],
                  "close": [10.0, 0.0],            # imputed bankruptcy terminal = 0 -> -100%
                  "source": ["yfinance", "imputed_bankruptcy"]}).to_parquet(
        tmp_path / "edgar" / "dead_name_prices.parquet")
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    gr._DEAD["path"] = None                          # reset the path-keyed cache for isolation
    s = gr._closes("DEAD")                           # no yahoo parquet -> falls back to dead store
    assert s is not None
    r = gr._ret(s, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01"))
    assert abs(r + 1.0) < 1e-9                        # 0/10 - 1 = -100% (loss counted, not dropped)


def test_non_overlapping_dedup():
    # three flags 30d apart (overlapping 90d horizons) collapse to ONE independent observation
    obs = [(pd.Timestamp("2026-01-01"), 1), (pd.Timestamp("2026-02-01"), 1),
           (pd.Timestamp("2026-03-01"), 1), (pd.Timestamp("2026-06-01"), 0)]   # last is >90d after first kept
    indep = gr._non_overlapping(obs, 90)
    assert indep == [1, 0]                            # 2026-01-01 then 2026-06-01 (others overlap)
