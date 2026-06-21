"""Tests for the S&P index-change announcement leg — collector parse + engine cohort/context."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from collectors import sp_index_changes as C  # noqa: E402
from engine import index_changes as IC  # noqa: E402


# --------------------------------------------------------------------------- #
# collector parsing (pure)
# --------------------------------------------------------------------------- #
_RSS = """<rss><channel>
<item><title>First Advantage Set to Join S&amp;P SmallCap 600</title>
<link>https://press.spglobal.com/2026-06-11-First-Advantage-Set-to-Join-S-P-SmallCap-600</link>
<pubDate>Thu, 11 Jun 2026 18:41:00 -0400</pubDate></item>
<item><title>S&amp;P Dow Jones Indices Announces Q2 Earnings</title>
<link>https://press.spglobal.com/2026-06-10-earnings</link>
<pubDate>Wed, 10 Jun 2026 09:00:00 -0400</pubDate></item>
</channel></rss>"""

_PAGE = """<html><body><table><tr><td>Effective Date</td><td>Index Name</td><td>Action</td>
<td>Company Name</td><td>Ticker</td><td>GICS Sector</td></tr>
<tr><td>June 16, 2026</td><td>S&amp;P SmallCap 600</td><td>Addition</td>
<td>First Advantage</td><td>FA</td><td>Industrials</td></tr>
<tr><td>June 16, 2026</td><td>S&amp;P SmallCap 600</td><td>Deletion</td>
<td>Kennedy-Wilson Holdings</td><td>KW</td><td>Real Estate</td></tr></table></body></html>"""


def test_parse_rss_keeps_only_join_items():
    items = C.parse_rss(_RSS)
    assert len(items) == 1
    assert items[0]["announce_date"] == "2026-06-11"
    assert "First-Advantage" in items[0]["url"]


def test_parse_changes_page_extracts_table():
    rows = C.parse_changes_page(_PAGE.replace("&amp;", "&"), "http://x/fa", "2026-06-11")
    by_t = {r["ticker"]: r for r in rows}
    assert by_t["FA"]["action"] == "addition" and by_t["FA"]["index"] == "sp600"
    assert by_t["FA"]["effective_date"] == "2026-06-16"
    assert by_t["KW"]["action"] == "deletion"
    assert all(r["announce_date"] == "2026-06-11" for r in rows)


# --------------------------------------------------------------------------- #
# engine cohort classification (pure)
# --------------------------------------------------------------------------- #
def _pit(rows):
    df = pd.DataFrame(rows)
    df["sd"] = pd.to_datetime(df["start_date"])
    df["ed"] = pd.to_datetime(df["end_date"])
    return {t: g for t, g in df.groupby("ticker")}


def test_classify_pure_when_no_prior_membership():
    assert IC.classify_cohort("NEW", "2026-06-16", "sp600", {}) == "pure"


def test_classify_migration_when_prior_other_index():
    # was active in sp400 until ~the add date, now joining sp500 → forced seller in sp400
    pit = _pit([{"ticker": "MIG", "start_date": "2024-01-01", "end_date": "2026-06-15", "src": "sp400"}])
    assert IC.classify_cohort("MIG", "2026-06-16", "sp500", pit) == "migration"


def test_classify_readd_when_prior_same_index():
    pit = _pit([{"ticker": "RE", "start_date": "2020-01-01", "end_date": "2023-01-01", "src": "sp600"}])
    assert IC.classify_cohort("RE", "2026-06-16", "sp600", pit) == "readd"


# --------------------------------------------------------------------------- #
# engine context snapshot
# --------------------------------------------------------------------------- #
def _changes():
    return pd.DataFrame([
        {"ticker": "FA", "index": "sp600", "action": "addition",
         "effective_date": "2026-06-16", "announce_date": "2026-06-11", "company": "First Advantage"},
        {"ticker": "MIG", "index": "sp500", "action": "addition",
         "effective_date": "2026-06-18", "announce_date": "2026-06-12", "company": "Migrator"},
        {"ticker": "OLD", "index": "sp600", "action": "addition",
         "effective_date": "2026-01-01", "announce_date": "2025-12-20", "company": "Stale"},  # too old
        {"ticker": "KW", "index": "sp600", "action": "deletion",
         "effective_date": "2026-06-16", "announce_date": "2026-06-11", "company": "Target"},  # deletion ignored
    ])


def test_build_snapshot_context_only_and_splits_cohorts(monkeypatch):
    pit = _pit([{"ticker": "MIG", "start_date": "2024-01-01", "end_date": "2026-06-17", "src": "sp400"}])
    monkeypatch.setattr(IC, "pit_history", lambda: pit)
    monkeypatch.setattr(IC, "load_gate", lambda: {"announce_gross_scored": True,
                                                  "announce_net_scored": False,
                                                  "announce_tiers": {"sp600": True, "sp500": True}})
    snap = IC.build_snapshot(today=date(2026, 6, 21), changes=_changes())
    assert snap["is_context_only"] is True and snap["scored"] is False
    assert snap["gate"]["gross_scored"] is True and snap["gate"]["net_scored"] is False
    pure = [r["ticker"] for r in snap["pure_additions"]]
    other = [r["ticker"] for r in snap["other_additions"]]
    assert "FA" in pure and "MIG" in other            # FA pure, MIG migration
    assert "OLD" not in pure + other                  # stale (>10d past) dropped
    assert "KW" not in pure + other                   # deletion ignored
    fa = next(r for r in snap["pure_additions"] if r["ticker"] == "FA")
    assert fa["days_to_effective"] == -5 and fa["run_up_window_open"] is True


def test_build_snapshot_degrades_empty():
    snap = IC.build_snapshot(today=date(2026, 6, 21), changes=pd.DataFrame())
    assert snap["n_pure"] == 0 and snap["scored"] is False and snap["schema"] == IC.SCHEMA


# --------------------------------------------------------------------------- #
# validator regression — thin windows (>=10 events, <8 distinct months) must NOT crash
# (newey_west_tstat returns t/p=None there; _window must fail closed, not float(None))
# --------------------------------------------------------------------------- #
def test_window_thin_months_fails_closed_not_crash(monkeypatch):
    import scripts.validate_index_reconstitution as R
    monkeypatch.setattr(R, "_abn", lambda prices, t, d, a, b: 0.01)
    ev = pd.DataFrame({"ticker": [f"T{i}" for i in range(12)],
                       "d": pd.to_datetime(["2026-01-05", "2026-01-12", "2026-02-03", "2026-02-10",
                                            "2026-03-02", "2026-03-09", "2026-04-06", "2026-04-13",
                                            "2026-01-20", "2026-02-17", "2026-03-16", "2026-04-20"])})
    w = R._window(ev, None, -5, 0)               # 12 events / 4 months → no HAC-t
    assert w["n"] == 12 and w["n_months"] == 4
    assert "hac_t" not in w                       # omitted, not None → consumers .get('hac_t',0)
    assert w.get("hac_t", 0) == 0                  # fail-closed: not scored, no crash
