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


# ---- W0a: new tests for multi-horizon grading + old-format tolerance ----

def test_multi_horizon_produces_per_horizon_slices(monkeypatch, tmp_path):
    """A flag logged 65 days ago is graded at 30d and 60d but still pending at 90d."""
    closes = {"MU": _series(140), "WDC": _series(135), "SPY": _series(110)}
    _patch(monkeypatch, tmp_path,
           [{"theme": "memory_storage", "asof": "2026-04-01", "stage": "PRECIPICE"}], closes)
    # today = 2026-06-05 → 65d elapsed → mature at 30/60, pending at 90
    s = gr.grade(today=pd.Timestamp("2026-06-05"), write=False)
    assert s["n_graded"] == 0    # canonical 90d not yet mature
    assert s["n_pending"] >= 1
    bh = s["by_horizon"]
    assert "30" in bh and "60" in bh and "90" in bh
    assert bh["30"]["n_graded"] == 1   # 30d matured
    assert bh["60"]["n_graded"] == 1   # 60d matured
    assert bh["90"]["n_graded"] == 0   # 90d not yet
    assert bh["90"]["n_pending"] == 1


def test_multi_horizon_independent_maturity(monkeypatch, tmp_path):
    """Horizons mature independently; a control-arm (RE-RATING) row grades at every horizon
    but carries NO hit-rate — forward excess only (beta, not skill)."""
    closes = {"MU": _series(150), "WDC": _series(145), "SPY": _series(105)}
    _patch(monkeypatch, tmp_path,
           [{"theme": "memory_storage", "asof": "2026-02-01", "stage": "RE-RATING"}], closes)
    # 2026-06-01 = ~120d → all horizons mature
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    bh = s["by_horizon"]
    for h in ["30", "60", "90"]:
        assert bh[h]["n_graded"] == 1
        # only control rows graded → no directional rows → no pooled hit-rate
        assert bh[h]["n_directional"] == 0
        assert bh[h]["pooled_hit_rate"] is None
    assert s["n_graded"] == 1   # canonical 90d graded (control rows still count as graded)


def test_control_arm_rerating_reports_excess_not_hit(monkeypatch, tmp_path):
    """RE-RATING is a control arm: theme >> SPY yields avg_excess > 0 but hit_rate=None —
    a crowded theme continuing to run must never be published as a 'hit' (beta ≠ skill)."""
    closes = {"MU": _series(150), "WDC": _series(145), "SPY": _series(105)}
    _patch(monkeypatch, tmp_path,
           [{"theme": "memory_storage", "asof": "2026-01-01", "stage": "RE-RATING"}], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    b = s["by_stage"]["RE-RATING"]
    assert b["n"] == 1 and b["n_dir"] == 0
    assert b["hit_rate"] is None and b["ci95"] is None
    assert b["avg_excess_pct"] is not None and b["avg_excess_pct"] > 0
    # control rows are excluded from the sign test / FDR machinery entirely
    assert s["by_theme"]["memory_storage"]["n_independent"] == 0
    assert s["pooled_hit_rate"] is None and s["pooled_n_directional"] == 0


def test_glut_risk_stage_is_exit_direction(monkeypatch, tmp_path):
    """GLUT-RISK rows from the foresight ledger are negative calls: theme << SPY = HIT."""
    closes = {"MU": _series(90), "WDC": _series(85), "SPY": _series(115)}
    _patch(monkeypatch, tmp_path,
           [{"theme": "memory_storage", "asof": "2026-01-01", "stage": "GLUT-RISK"}], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    b = s["by_stage"]["GLUT-RISK"]
    assert b["n_dir"] == 1 and b["hits"] == 1 and b["hit_rate"] == 1.0


def test_text_grade_precipice_inherits_thesis_direction(monkeypatch, tmp_path):
    """'PRECIPICE (text)' (the W1a text-grade stage) inherits the thesis role: outperform = hit."""
    closes = {"MU": _series(150), "WDC": _series(145), "SPY": _series(105)}
    _patch(monkeypatch, tmp_path,
           [{"theme": "memory_storage", "asof": "2026-01-01", "stage": "PRECIPICE (text)"}], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    b = s["by_stage"]["PRECIPICE (text)"]
    assert b["n_dir"] == 1 and b["hits"] == 1 and b["hit_rate"] == 1.0


def test_old_single_horizon_ledger_rows_tolerated(monkeypatch, tmp_path):
    """Old-format rows (no 'horizons' field) are tolerated — graded at each HORIZONS entry."""
    closes = {"MU": _series(140), "WDC": _series(135), "SPY": _series(110)}
    # old-format row: no 'horizons' key, just asof + stage (original format)
    old_row = {"theme": "memory_storage", "asof": "2026-01-01", "stage": "PRECIPICE"}
    _patch(monkeypatch, tmp_path, [old_row], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    # should grade at all horizons without error
    assert s["n_graded"] == 1
    bh = s["by_horizon"]
    assert all(bh[str(h)]["n_graded"] == 1 for h in [30, 60, 90])


def test_by_horizon_in_output_structure(monkeypatch, tmp_path):
    """by_horizon key exists in output with correct structure keys."""
    closes = {"MU": _series(140), "WDC": _series(135), "SPY": _series(110)}
    _patch(monkeypatch, tmp_path,
           [{"theme": "memory_storage", "asof": "2026-01-01", "stage": "WATCH"}], closes)
    s = gr.grade(today=pd.Timestamp("2026-06-01"), write=False)
    assert "by_horizon" in s
    assert "horizons" in s
    assert s["horizons"] == [30, 60, 90]
    for h_key in ["30", "60", "90"]:
        assert h_key in s["by_horizon"]
        bh = s["by_horizon"][h_key]
        assert "horizon_days" in bh and "n_graded" in bh and "n_pending" in bh
        assert "by_stage" in bh and "by_theme" in bh
