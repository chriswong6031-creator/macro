"""engine.subsector_scan — the cascade signature over the Finviz 113-subsector taxonomy.
Verifies the per-subsector stage logic (scarcity x revision breadth), the member threshold,
and graceful None. Pure via _scan_rows with a synthetic revisions frame.
"""
from __future__ import annotations

import pandas as pd

from engine import subsector_scan as ss


def _latest(rows: dict):
    """rows: {ticker: (breadth, n_analysts, est_chg_90d)} -> a revisions frame indexed by ticker."""
    recs = [{"breadth": b, "net_up_30d": b, "est_chg_30d": d, "est_chg_90d": d,
             "n_analysts": n, "asof": "2026-06-28"} for (b, n, d) in rows.values()]
    return pd.DataFrame(recs, index=list(rows))


def test_scarcity_plus_flat_revisions_is_precipice():
    imap = {("Technology", "Semiconductors"): ["AAA", "BBB", "CCC"]}
    latest = _latest({"AAA": (0.0, 5, 0.0), "BBB": (0.05, 5, 0.0), "CCC": (0.0, 5, 0.0)})
    rows = ss._scan_rows(imap, latest, None, scarce={"AAA", "BBB"})
    assert len(rows) == 1
    assert rows[0]["stage"] == "PRECIPICE" and rows[0]["n_scarcity"] == 2


def test_scarcity_plus_rising_is_broadening():
    imap = {("Technology", "Semiconductors"): ["AAA", "BBB", "CCC"]}
    latest = _latest({"AAA": (0.4, 5, 10.0), "BBB": (0.5, 5, 10.0), "CCC": (0.3, 5, 10.0)})
    rows = ss._scan_rows(imap, latest, None, scarce={"AAA", "BBB"})
    assert rows[0]["stage"] == "BROADENING"


def test_broad_revisions_without_scarcity_is_rerating():
    imap = {("Technology", "Semiconductors"): ["AAA", "BBB", "CCC"]}
    latest = _latest({"AAA": (0.8, 5, 15.0), "BBB": (0.9, 5, 15.0), "CCC": (0.85, 5, 15.0)})
    rows = ss._scan_rows(imap, latest, None, scarce=set())
    assert rows[0]["stage"] == "RE-RATING" and rows[0]["n_scarcity"] == 0


def test_below_min_members_skipped():
    imap = {("X", "Y"): ["AAA", "BBB"]}                  # 2 < MIN_MEMBERS
    latest = _latest({"AAA": (0.0, 5, 0.0), "BBB": (0.0, 5, 0.0)})
    assert ss._scan_rows(imap, latest, None, scarce=set()) == []


def test_ranks_precipice_before_rerating():
    imap = {("Tech", "A"): ["AAA", "BBB", "CCC"], ("Tech", "B"): ["DDD", "EEE", "FFF"]}
    latest = _latest({"AAA": (0.0, 5, 0.0), "BBB": (0.05, 5, 0.0), "CCC": (0.0, 5, 0.0),
                      "DDD": (0.9, 5, 15.0), "EEE": (0.85, 5, 15.0), "FFF": (0.8, 5, 15.0)})
    rows = ss._scan_rows(imap, latest, None, scarce={"AAA", "BBB"})        # A is the precipice
    assert rows[0]["sub_industry"] == "A" and rows[0]["stage"] == "PRECIPICE"


def test_compute_none_without_map(monkeypatch):
    monkeypatch.setattr(ss, "_industry_map", lambda: None)
    assert ss.compute_subsector_scan(write_ledger=False) is None
