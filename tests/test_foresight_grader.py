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
