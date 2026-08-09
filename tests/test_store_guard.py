"""check_coverage_regression: a degraded recompute must not overwrite a good store.

2026-08-08 incident (commit 901282ec209): the weekly deep-dive recomputed the HK
regime history with a stale runner-workspace constituent-close cache while the
cpi/ppi ffill budget had run out, so the inflation axis went NaN for the last 9
sessions. weekly.yml's W0b guard then discarded the degraded parquet but shipped
site/hk_regime_timeline.json built from it — a committed artifact contradicting
the committed store in the same tree, and the nulls crashed the landing hub.
The guard refuses the overwrite so callers abort (build_hk skips the HK pages)
and the previous committed state keeps serving.

Run: .venv/bin/python -m pytest tests/test_store_guard.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.store_guard import ESCAPE_ENV, check_coverage_regression

IDX = pd.bdate_range("2026-07-06", "2026-08-07")


def _seed(tmp_path, idx=IDX):
    old = pd.DataFrame(
        {"growth_score": 0.1, "inflation_score": 0.0, "quad": "Goldilocks"},
        index=idx)
    path = tmp_path / "regime_history.parquet"
    old.to_parquet(path)
    return old, path


def test_trailing_null_regression_refuses_and_warns_line_start(tmp_path, capsys):
    old, path = _seed(tmp_path)
    new = old.copy()
    new.loc[new.index[-9:], "inflation_score"] = np.nan   # the incident shape
    with pytest.raises(RuntimeError, match="regresses coverage"):
        check_coverage_regression(new, path, "hk")
    out = capsys.readouterr().out
    warn = [l for l in out.splitlines() if "coverage-regression" in l]
    assert warn and warn[0].startswith("::warning ")   # annotation must START the line
    assert "inflation_score: 9 cells" in warn[0]
    assert "2026-07-28..2026-08-07" in warn[0]
    # the store itself is untouched
    pd.testing.assert_frame_equal(pd.read_parquet(path), old, check_freq=False)


def test_string_column_regression_refuses(tmp_path):
    old, path = _seed(tmp_path)
    new = old.copy()
    new.loc[new.index[-1], "quad"] = None
    with pytest.raises(RuntimeError):
        check_coverage_regression(new, path, "hk")


def test_end_shrink_refuses(tmp_path):
    old, path = _seed(tmp_path)
    new = old.iloc[:-3]
    with pytest.raises(RuntimeError, match="end moved backwards"):
        check_coverage_regression(new, path, "hk")


def test_escape_env_warns_but_allows(tmp_path, capsys, monkeypatch):
    old, path = _seed(tmp_path)
    new = old.copy()
    new.loc[new.index[-1], "inflation_score"] = np.nan
    monkeypatch.setenv(ESCAPE_ENV, "1")
    check_coverage_regression(new, path, "hk")   # no raise
    assert any(l.startswith("::warning ") for l in capsys.readouterr().out.splitlines())


def test_value_changes_pass(tmp_path):
    old, path = _seed(tmp_path)
    new = old.copy()
    new["growth_score"] = new["growth_score"] + 0.35   # recalibration / revision
    check_coverage_regression(new, path, "hk")


def test_new_trailing_dates_may_be_null(tmp_path):
    old, path = _seed(tmp_path)
    ext = pd.bdate_range(IDX[0], "2026-08-11")
    new = old.reindex(ext)
    new.loc[ext[-2:], "growth_score"] = np.nan   # honest not-computable-yet days
    check_coverage_regression(new, path, "hk")


def test_new_and_dropped_columns_pass(tmp_path):
    old, path = _seed(tmp_path)
    new = old.drop(columns=["quad"]).assign(cycle="expansion")   # schema change
    check_coverage_regression(new, path, "hk")


def test_state_null_column_relocation_passes(tmp_path):
    # pending_quad's null MEANS "no flip pending" — value drift relocates its
    # episodes on every honest recompute; the guard must not read that as loss.
    old, path = _seed(tmp_path)
    old["pending_quad"] = None
    old.loc[old.index[5:10], "pending_quad"] = "Reflation"
    old.to_parquet(path)
    new = old.copy()
    new["pending_quad"] = None
    new.loc[new.index[12:14], "pending_quad"] = "Stagflation"
    check_coverage_regression(new, path, "hk")


def test_cold_start_passes(tmp_path):
    new = pd.DataFrame({"growth_score": 0.1}, index=IDX)
    check_coverage_regression(new, tmp_path / "regime_history.parquet", "hk")


def test_unreadable_store_passes(tmp_path):
    path = tmp_path / "regime_history.parquet"
    path.write_bytes(b"not a parquet")
    new = pd.DataFrame({"growth_score": 0.1}, index=IDX)
    check_coverage_regression(new, path, "hk")


def test_every_regime_engine_wires_the_guard():
    # All four regimes recompute-in-place, and intraday lanes (engine-render,
    # weekly pre-#5047) ship site/ from the recompute while discarding data/ —
    # an unguarded engine re-opens the 2026-08-08 self-contradicting-commit
    # class for its region. Pin the wiring so a refactor can't drop one
    # silently (the HK gap survived exactly because only China took the
    # sibling fix).
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "engine"
    for mod in ("run.py", "canada_run.py", "china_run.py", "hk_run.py"):
        src = (root / mod).read_text()
        write = src.index('to_parquet(p / "regime_history.parquet")')
        guard = src.find("check_coverage_regression(store_df,")
        assert 0 <= guard < write, f"engine/{mod} writes regime_history.parquet unguarded"
