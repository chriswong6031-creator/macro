"""CCW-W1 / §2.2-R12: guard the 9 BAML rolling-series archive snapshots.

These archives are seeded by scripts/snapshot_fred_archive.py (one-shot, run once
after CCW-W1 lands).  The files are gitignored binary data, so in a clean CI
checkout they will be absent — the tests skip cleanly in that case.  On the Mac
Studio nightly host (and any checkout where the script has been run) all 9 files
must pass structural invariants:
  - loads as a pandas DataFrame
  - DatetimeIndex named 'date'
  - exactly one column, named by the config alias
  - more than 500 rows (rolling 3y window ≈ 785 trading days)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]

# Series ID → expected column alias (mirrors config.yml [fred][series][corp_credit])
EXPECTED = {
    "BAMLC0A1CAAA":    "aaa_oas",
    "BAMLC0A2CAA":     "aa_oas",
    "BAMLC0A3CA":      "a_oas",
    "BAMLC0A4CBBB":    "bbb_oas",
    "BAMLH0A1HYBB":    "bb_oas",
    "BAMLH0A2HYB":     "b_oas",
    "BAMLC0A0CMEY":    "ig_eff_yield",
    "BAMLH0A0HYM2EY":  "hy_eff_yield",
    "BAMLCC0A0CMTRIV": "ig_total_return",
}

ARCHIVE_DIR = ROOT / "data" / "archive"


@pytest.mark.parametrize("sid,col", sorted(EXPECTED.items()))
def test_baml_archive_structure(sid: str, col: str) -> None:
    """Archive parquet for this series loads with correct DatetimeIndex and column."""
    path = ARCHIVE_DIR / f"{sid}.parquet"
    if not path.exists():
        pytest.skip(f"{sid}: archive not present at {path} — run scripts/snapshot_fred_archive.py")

    df = pd.read_parquet(path)

    assert isinstance(df.index, pd.DatetimeIndex), (
        f"{sid}: index is not DatetimeIndex (got {type(df.index).__name__})"
    )
    assert df.index.name == "date", (
        f"{sid}: index.name should be 'date', got {df.index.name!r}"
    )
    assert list(df.columns) == [col], (
        f"{sid}: expected single column [{col!r}], got {list(df.columns)}"
    )
    assert len(df) > 500, (
        f"{sid}: expected >500 rows (rolling 3y window), got {len(df)}"
    )
    assert df[col].dtype == float or pd.api.types.is_float_dtype(df[col]), (
        f"{sid}: column {col!r} should be float, got {df[col].dtype}"
    )
    assert df[col].notna().all(), (
        f"{sid}: {df[col].isna().sum()} NaN values in archive (archive must be clean)"
    )
