"""De-biased universe wiring in engine/equity_factors._closes (Phase 1A/1B capstone).

The load-bearing invariant is SELF-GATING: `_closes("debiased")` equals
`_closes("broad")` exactly while no dead-name prices are recovered, and grows to
include dead names (new columns) once they are — so wiring it in is risk-free and it
de-biases automatically as CI accrues delisted prices.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import engine.equity_factors as ef


def _broad_cache(tmp_path, tickers=("AAA", "BBB"), n=40):
    (tmp_path / "breadth").mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range("2024-01-01", periods=n)
    rng = np.random.default_rng(0)
    df = pd.DataFrame({t: 100 * np.cumprod(1 + rng.normal(0, 0.01, n)) for t in tickers}, index=idx)
    df.to_parquet(tmp_path / "breadth" / "_closes_cache.parquet")
    return idx


def test_debiased_equals_broad_when_no_dead_prices(monkeypatch, tmp_path):
    _broad_cache(tmp_path)
    monkeypatch.setattr(ef.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr("collectors.edgar_deadname_prices.dead_name_closes", lambda: pd.DataFrame())
    broad = ef._closes("broad")
    deb = ef._closes("debiased")
    pd.testing.assert_frame_equal(broad, deb)            # SELF-GATING: identical


def test_debiased_adds_dead_names_when_present(monkeypatch, tmp_path):
    idx = _broad_cache(tmp_path)
    monkeypatch.setattr(ef.config, "data_dir", lambda: tmp_path)
    dead = pd.DataFrame({"DEADCO": np.linspace(5, 9, len(idx))}, index=idx)
    monkeypatch.setattr("collectors.edgar_deadname_prices.dead_name_closes", lambda: dead)
    deb = ef._closes("debiased")
    assert "DEADCO" in deb.columns                       # the delisted cohort enters
    assert set(deb.columns) == {"AAA", "BBB", "DEADCO"}
    assert deb["DEADCO"].iloc[0] == 5.0


def test_debiased_survivor_wins_on_column_collision(monkeypatch, tmp_path):
    idx = _broad_cache(tmp_path, tickers=("AAA", "BBB"))
    monkeypatch.setattr(ef.config, "data_dir", lambda: tmp_path)
    # a name already in the survivor cache must not be overwritten by a dead frame
    dead = pd.DataFrame({"AAA": np.full(len(idx), -1.0)}, index=idx)
    monkeypatch.setattr("collectors.edgar_deadname_prices.dead_name_closes", lambda: dead)
    deb = ef._closes("debiased")
    assert (deb["AAA"] > 0).all()                        # survivor AAA kept, not the -1 dead one
