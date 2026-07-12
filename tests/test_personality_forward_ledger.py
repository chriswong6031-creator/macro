"""W2b personality forward-ledger stamper (scripts/build_stock_library.py).

track_record appends buy/rebuy rows RETROACTIVELY (~3-4 sessions after the fire
date — the pending-quality anti-repaint gate in engine/track_record.py), so the
stamper must catch fires dated BEFORE build_date. The original `date == build_date`
filter matched nothing, ever (found + fixed 2026-07-12; see NWCI masterplan R-CI12).
"""
from __future__ import annotations

import pandas as pd

from scripts.build_stock_library import _stamp_personality_forward_ledger


class _Cfg:
    def __init__(self, root):
        self._root = root

    def data_dir(self):
        return self._root


_SP = {
    "base": {
        "archetype": {"key": "mixed"},
        "dna_class": {"key": "grinder"},
        "chart_personality": {"labels": ["x"]},
        "ownership_habitat": {"labels": ["y"]},
        "microstructure": {"labels": ["z"]},
    },
    "current_mode": {"modes": ["m"]},
}


def _write_tr(root, rows):
    d = root / "signal_archive"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(d / "track_record.parquet", index=False)


def test_stamps_retroactive_fires_dedups_and_floors(tmp_path):
    _write_tr(tmp_path, [
        {"ticker": "TTD", "date": "2026-07-06", "type": "buy"},    # 4 sessions before build
        {"ticker": "SBUX", "date": "2026-07-07", "type": "buy"},
        {"ticker": "OLD", "date": "2026-07-01", "type": "buy"},    # pre-wire-in floor → excluded
        {"ticker": "TTD", "date": "2026-07-09", "type": "sell"},   # not an entry type
    ])
    sp = {"TTD": _SP, "SBUX": _SP, "OLD": _SP}
    cfg = _Cfg(tmp_path)

    _stamp_personality_forward_ledger(sp, "2026-07-10", cfg)
    fl = pd.read_parquet(tmp_path / "stock_personality" / "forward_ledger.parquet")
    assert sorted(zip(fl["ticker"], fl["date"])) == [
        ("SBUX", "2026-07-07"), ("TTD", "2026-07-06")]
    assert set(fl["stamped_on"]) == {"2026-07-10"}
    assert set(fl["type"]) == {"buy"}

    # next nightly: same fires still inside the window → dedup keeps them single;
    # a new retro-appended rebuy is picked up.
    _write_tr(tmp_path, [
        {"ticker": "TTD", "date": "2026-07-06", "type": "buy"},
        {"ticker": "SBUX", "date": "2026-07-07", "type": "buy"},
        {"ticker": "NEW", "date": "2026-07-10", "type": "rebuy"},
    ])
    sp["NEW"] = _SP
    _stamp_personality_forward_ledger(sp, "2026-07-11", cfg)
    fl = pd.read_parquet(tmp_path / "stock_personality" / "forward_ledger.parquet")
    assert len(fl) == 3
    assert set(fl["ticker"]) == {"TTD", "SBUX", "NEW"}
    assert fl.loc[fl["ticker"] == "NEW", "stamped_on"].item() == "2026-07-11"


def test_no_entry_fires_leaves_ledger_absent(tmp_path):
    _write_tr(tmp_path, [
        {"ticker": "TTD", "date": "2026-07-09", "type": "sell"},
        {"ticker": "SBUX", "date": "2026-07-09", "type": "near_miss"},
    ])
    cfg = _Cfg(tmp_path)
    _stamp_personality_forward_ledger({"TTD": _SP, "SBUX": _SP}, "2026-07-10", cfg)
    assert not (tmp_path / "stock_personality" / "forward_ledger.parquet").exists()
