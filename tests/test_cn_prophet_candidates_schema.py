"""The CN candidate store's stamp column is ``stamp_date`` — never ``date``.

Adjudicated 2026-08-04 (``research/CONTEXT_VECTOR_SCHEMA_CONTRACT.md`` §3.1, cross-market
spine law §7 of ``research/PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md``): the CN and
US context-vector stores are one schema family and its stamp column is ``stamp_date``.
The US store already shipped it; the CN store was renamed here, one-time, in place.

Two tests that fail for DIFFERENT reasons on purpose:

1. **The committed bytes.** ``data/china_prophet_rank/candidates.parquet`` is git-tracked,
   so a checkout that carries the old ``date`` column — a bad rebase, a revert of the
   one-time rewrite, a nightly run from a pre-rename engine — is caught by reading the
   parquet FOOTER only (no data load, no pandas). The file's absence is a FAILURE, never a
   skip: a tracked artifact that vanished is a broken checkout, and a skip here would make
   the pin quietly dark.

2. **The writer.** The committed bytes could be correct while a re-introduced ``"date"``
   key in ``engine/china_prophet_shadow.py`` re-creates the old column on the very next
   nightly append. Test 2 appends through the public ``append_candidates`` API into a tmp
   store and reads the result back, so the writer is pinned wherever its output lands.

Run: python3 -m pytest tests/test_cn_prophet_candidates_schema.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import china_prophet_shadow as shadow  # noqa: E402
from lib import config  # noqa: E402

STORE = ROOT / "data" / "china_prophet_rank" / "candidates.parquet"


# ---------------------------------------------------------------------------
# 1. the committed store
# ---------------------------------------------------------------------------
def test_the_committed_candidate_store_stamps_stamp_date():
    assert STORE.exists(), (
        f"{STORE.relative_to(ROOT)} is git-tracked and missing — broken checkout, "
        "not a reason to skip this pin"
    )
    names = pq.ParquetFile(STORE).schema_arrow.names
    assert "stamp_date" in names, (
        "the committed CN candidate store lost its stamp_date column — "
        "cross-market schema contract §3.1"
    )
    assert "date" not in names, (
        "the pre-rename 'date' column is back in the committed CN candidate store — "
        "a pre-rename engine or a reverted one-time rewrite wrote it"
    )


# ---------------------------------------------------------------------------
# 2. the writer
# ---------------------------------------------------------------------------
def _candidate(ticker: str = "600001.SS") -> dict:
    """One raw-eligible candidate — the minimum ``append_candidates`` will store."""
    return {
        "ticker": ticker,
        "name": f"Name {ticker}",
        "sector": "Industrials",
        "board_definition": "cn_prophet_v2",
        "prophet_score": 70.0,
        "signal": {
            "eligible": True,
            "tier_cascade": "T2",
            "reason": "test gate",
            "asof": "2026-07-29",
            "input_asof": "2026-07-29",
        },
        "entry_signal": {"status": "buy_now", "urgency": "now"},
        "_board_asof": "2026-07-29",
        "price": 10.0,
    }


def test_the_writer_stamps_stamp_date_on_a_fresh_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        shadow.china_standout_track,
        "session_status",
        lambda asof: {"partial_session": False, "reason": "settled"},
    )

    row = _candidate()
    assert shadow.append_candidates(
        [row],
        "2026-07-29",
        lane="asia",
        board_lanes={"featured": [{**row, "display_rank": 1}]},
    ) == 1

    stored = pd.read_parquet(shadow._store_path())
    assert "stamp_date" in stored.columns, "the writer stopped stamping stamp_date"
    assert "date" not in stored.columns, "the writer re-introduced the pre-rename column"
    assert stored["stamp_date"].tolist() == ["2026-07-29"]
