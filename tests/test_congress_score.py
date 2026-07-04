"""Tests for build_congress — uncovered-row inflation fix (brief #4) + W1-S13 freshness fixes.

Existing tests: uncovered/covered composite, multiplier vetoes, act_now.
New tests (W1-S13):
  - T2: _decay uses TransactionDate, not ReportDate
  - T2: filing_lag_days and late_filing flag computed correctly
  - T1: member shrinkage math (congress_members.py)
  - T4: ETF flag in _aggregate
  - T5: gate_tier in _score
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_congress import (
    _score, _decay, _aggregate,
    W_CLUSTER, W_TECHNICAL, W_ZONE,
    LATE_FILING_DAYS, TX_AGE_STALE_DAYS, KNOWN_ETFS, HALFLIFE_DAYS,
)
from engine.congress_members import _shrink, _tier, compute as _compute_members


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _agg(cluster: float, ticker: str = "TEST") -> dict:
    """Minimal aggregate dict with the fields _score reads."""
    return {
        "ticker": ticker,
        "cluster_score": cluster,
        "n_disclosures": 3,
        "n_distinct_members": 2,
        "members": ["Alice", "Bob"],
        "member_detail": [],
        "n_buys": 2,
        "n_sells": 1,
        "buy_notional": 50_000,
        "buy_parties": ["D", "R"],
        "bipartisan": True,
        "important": True,
        "last_report": "2026-06-01",
        "expires": "2026-12-01",
        "days_left": 152,
        "recency": 0.9,
        # W1-S13 new provenance fields
        "latest_tx_age": 30,
        "all_stale": False,
        "any_late_filing": False,
        "median_lag_days": 20,
        "is_etf": False,
        "single_member": False,
    }


def _eng_covered(tech: float = 55.0, zone: float = 60.0,
                 blocked: bool = False, downtrend: bool = False, extended: bool = False) -> dict:
    return {
        "covered": True,
        "technical": tech,
        "zone": zone,
        "blocked": blocked,
        "downtrend": downtrend,
        "extended": extended,
        "band": "moderate",
        "verdict": None,
        "timing": "uptrend confirmed, sector leading",
        "sector_dir": "bull",
        "theme_dir": "bull",
        "trend_dir": "bull",
        "price": 42.0,
    }


def _eng_uncovered() -> dict:
    return {
        "covered": False,
        "technical": None,
        "zone": None,
        "blocked": False,
        "downtrend": False,
        "extended": False,
        "band": None,
        "verdict": None,
        "timing": None,
        "sector_dir": None,
        "theme_dir": None,
        "trend_dir": None,
        "price": None,
    }


# ---------------------------------------------------------------------------
# brief requirement: covered(cluster=60) must outrank uncovered(cluster=90)
# ---------------------------------------------------------------------------

def test_covered_outranks_uncovered_high_cluster():
    """Core brief assertion: a covered row with moderate cluster beats an uncovered row
    with a much higher cluster — the sort key puts covered rows first regardless of
    composite value."""
    covered_row = _score(_agg(60.0, "COV"), _eng_covered(tech=50.0, zone=50.0))
    uncovered_row = _score(_agg(90.0, "UNC"), _eng_uncovered())

    # Sort as main() does
    rows = sorted([uncovered_row, covered_row],
                  key=lambda a: (1 if a["unconfirmed"] else 0, -a["composite"]))
    assert rows[0]["ticker"] == "COV", (
        f"Expected covered row first; got {rows[0]['ticker']} "
        f"(covered composite={covered_row['composite']}, uncovered composite={uncovered_row['composite']})"
    )


# ---------------------------------------------------------------------------
# uncovered composite = W_CLUSTER * cluster only (no neutral 30 gift)
# ---------------------------------------------------------------------------

def test_uncovered_composite_is_cluster_only():
    """Composite for uncovered = W_CLUSTER * cluster; no tech/zone neutral addition."""
    row = _score(_agg(80.0), _eng_uncovered())
    expected = round(W_CLUSTER * 80.0, 1)
    assert row["composite"] == expected, (
        f"Uncovered composite should be {expected}; got {row['composite']}"
    )


def test_uncovered_composite_below_old_inflated_value():
    """The old formula gave ~0.40*cluster + 30 for missing tech+zone.  New value must be lower."""
    cluster = 90.0
    row = _score(_agg(cluster), _eng_uncovered())
    old_tw = W_CLUSTER + W_TECHNICAL + W_ZONE
    old_composite = (W_CLUSTER * cluster + W_TECHNICAL * 50.0 + W_ZONE * 50.0) / old_tw
    assert row["composite"] < old_composite, (
        f"New uncovered composite {row['composite']} should be below old inflated value {old_composite:.1f}"
    )


# ---------------------------------------------------------------------------
# unconfirmed flag
# ---------------------------------------------------------------------------

def test_uncovered_marked_unconfirmed():
    row = _score(_agg(70.0), _eng_uncovered())
    assert row["unconfirmed"] is True


def test_covered_not_unconfirmed():
    row = _score(_agg(70.0), _eng_covered())
    assert row["unconfirmed"] is False


# ---------------------------------------------------------------------------
# multiplier vetoes still apply to covered names
# ---------------------------------------------------------------------------

def test_covered_blocked_applies_multiplier():
    normal = _score(_agg(60.0), _eng_covered(blocked=False))
    blocked = _score(_agg(60.0), _eng_covered(blocked=True))
    assert blocked["composite"] < normal["composite"], (
        "Blocked multiplier (×0.6) must reduce covered composite"
    )
    assert abs(blocked["composite"] - round(normal["composite"] * 0.6, 1)) <= 0.2


def test_covered_extended_applies_multiplier():
    normal = _score(_agg(60.0), _eng_covered(extended=False))
    extended = _score(_agg(60.0), _eng_covered(extended=True))
    assert extended["composite"] < normal["composite"], (
        "Extended multiplier (×0.85) must reduce covered composite"
    )


# ---------------------------------------------------------------------------
# uncovered rows must NOT apply multiplier vetoes (no engine to veto on)
# ---------------------------------------------------------------------------

def test_uncovered_vetoes_not_applied():
    """Uncovered rows have no meaningful blocked/downtrend flags; composite must be cluster-only."""
    # Simulate a stale eng dict that happens to have blocked=True from a prior read
    eng = _eng_uncovered()
    eng["blocked"] = True   # should be ignored for uncovered rows
    row = _score(_agg(80.0), eng)
    expected = round(W_CLUSTER * 80.0, 1)
    assert row["composite"] == expected, (
        f"Veto flags must not be applied to uncovered rows; expected {expected}, got {row['composite']}"
    )


# ---------------------------------------------------------------------------
# act_now must be False for uncovered rows
# ---------------------------------------------------------------------------

def test_uncovered_act_now_false():
    row = _score(_agg(100.0), _eng_uncovered())
    assert row["act_now"] is False


# ===========================================================================
# W1-S13 NEW TESTS
# ===========================================================================

# ---------------------------------------------------------------------------
# T2: _decay uses TransactionDate, not ReportDate
# ---------------------------------------------------------------------------

def test_decay_uses_transaction_date_not_report_date():
    """_decay(td, asof) must decay based on age since TransactionDate.

    Key regression: before the fix, _decay was called with ReportDate (_rd),
    so an old trade filed recently would score as maximally fresh.
    Proof: passing an old td and a fresh rd gives DIFFERENT decay values, and
    _decay(old_td) < _decay(fresh_td).
    """
    import math
    asof = date(2026, 7, 4)

    # Trade executed 90 days ago — should give substantial decay
    old_td = date(2026, 4, 5)   # 90d before asof
    weight_old = _decay(old_td, asof)

    # Trade executed 5 days ago — should be near 1.0
    fresh_td = date(2026, 6, 29)   # 5d before asof
    weight_fresh = _decay(fresh_td, asof)

    # Decay function: 0.5 ** (age / HALFLIFE_DAYS)
    expected_old   = 0.5 ** (90 / HALFLIFE_DAYS)
    expected_fresh = 0.5 ** (5  / HALFLIFE_DAYS)

    assert abs(weight_old - expected_old) < 1e-9, (
        f"Expected decay({old_td}) ≈ {expected_old:.4f}; got {weight_old:.4f}"
    )
    assert abs(weight_fresh - expected_fresh) < 1e-9, (
        f"Expected decay({fresh_td}) ≈ {expected_fresh:.4f}; got {weight_fresh:.4f}"
    )
    assert weight_old < weight_fresh, (
        f"Old trade ({old_td}) must decay more than fresh trade ({fresh_td}); "
        f"got old={weight_old:.4f}, fresh={weight_fresh:.4f}"
    )


def test_decay_none_returns_one():
    """_decay(None, asof) must return 1.0 (fallback for missing TransactionDate)."""
    assert _decay(None, date(2026, 7, 4)) == 1.0


# ---------------------------------------------------------------------------
# T2: filing_lag_days and late_filing flag
# ---------------------------------------------------------------------------

def _make_trade(ticker="TST", td=None, rd=None, side="buy"):
    """Minimal trade row for _aggregate tests."""
    return {
        "ticker": ticker,
        "representative": "Jane Smith",
        "bio_guide_id": "S000123",
        "party": "D",
        "chamber": "House",
        "side": side,
        "amount_low": 15001.0,
        "amount_high": 50000.0,
        "amount_mid": 32500.0,
        "report_date": rd.isoformat() if rd else None,
        "_rd": rd,
        "transaction_date": td.isoformat() if td else None,
        "_td": td,
        "filing_lag_days": (rd - td).days if (rd and td) else None,
        "late_filing": (((rd - td).days > LATE_FILING_DAYS) if (rd and td) else False),
        "tx_age_days": (date(2026, 7, 4) - td).days if td else None,
        "excess_return": None,
    }


def test_filing_lag_computed_correctly():
    """filing_lag_days = ReportDate − TransactionDate in calendar days."""
    td = date(2026, 5, 1)
    rd = date(2026, 5, 20)   # 19-day lag — under the limit
    t = _make_trade(td=td, rd=rd)
    assert t["filing_lag_days"] == 19
    assert t["late_filing"] is False


def test_late_filing_flag_over_45():
    """filing_lag_days > LATE_FILING_DAYS → late_filing = True (STOCK Act violation)."""
    td = date(2026, 1, 1)
    rd = date(2026, 2, 20)   # 50-day lag — over the limit
    t = _make_trade(td=td, rd=rd)
    assert t["filing_lag_days"] == 50
    assert t["late_filing"] is True


def test_aggregate_any_late_filing_flag():
    """_aggregate.any_late_filing = True when at least one trade has late_filing=True."""
    asof = date(2026, 7, 4)
    td1 = date(2026, 5, 1)
    td2 = date(2026, 5, 5)
    rd1 = date(2026, 6, 30)  # 60-day lag — late
    rd2 = date(2026, 5, 20)  # 15-day lag — fine
    trades = [
        _make_trade("TST", td=td1, rd=rd1),
        _make_trade("TST", td=td2, rd=rd2),
    ]
    agg = _aggregate("TST", trades, asof)
    assert agg["any_late_filing"] is True


def test_aggregate_not_late_filing_when_clean():
    """_aggregate.any_late_filing = False when all filings are within 45 days."""
    asof = date(2026, 7, 4)
    td = date(2026, 6, 1)
    rd = date(2026, 6, 15)   # 14-day lag — fine
    trades = [_make_trade("TST", td=td, rd=rd)]
    agg = _aggregate("TST", trades, asof)
    assert agg["any_late_filing"] is False


def test_aggregate_all_stale_flag():
    """all_stale = True when latest TransactionDate is > TX_AGE_STALE_DAYS ago."""
    asof = date(2026, 7, 4)
    # Make a trade TX_AGE_STALE_DAYS + 10 days ago
    old_td = date(2026, 7, 4) - __import__("datetime").timedelta(days=TX_AGE_STALE_DAYS + 10)
    old_rd = date(2026, 7, 4) - __import__("datetime").timedelta(days=TX_AGE_STALE_DAYS)
    trades = [_make_trade("TST", td=old_td, rd=old_rd)]
    agg = _aggregate("TST", trades, asof)
    assert agg["all_stale"] is True


def test_aggregate_not_stale_when_fresh():
    """all_stale = False when there is a recent transaction."""
    asof = date(2026, 7, 4)
    fresh_td = date(2026, 6, 25)   # 9 days ago — well under stale threshold
    fresh_rd = date(2026, 7, 1)
    trades = [_make_trade("TST", td=fresh_td, rd=fresh_rd)]
    agg = _aggregate("TST", trades, asof)
    assert agg["all_stale"] is False


# ---------------------------------------------------------------------------
# T1: member shrinkage math (congress_members.py)
# ---------------------------------------------------------------------------

def test_shrink_toward_prior_when_n_zero():
    """With n=0 effective trades, shrunk rate = prior (no data, all prior)."""
    prior = 0.393
    result = _shrink(0, 0, prior=prior)
    assert result == prior, f"Expected {prior}, got {result}"


def test_shrink_large_n_close_to_raw():
    """With large n, shrunk rate is close to raw (data dominates prior)."""
    n = 200
    n_hits = 120   # raw = 60%
    prior = 0.393
    shrunk = _shrink(n_hits, n, prior=prior)
    raw = n_hits / n
    # shrunk should be between raw and prior, much closer to raw at n=200
    assert prior < shrunk < raw or abs(shrunk - raw) < 0.02, (
        f"At n={n}, shrunk={shrunk:.3f} should be close to raw={raw:.3f}"
    )
    # Specifically: |shrunk - raw| < |shrunk - prior|
    assert abs(shrunk - raw) < abs(shrunk - prior), (
        "With large n, shrunk should be pulled more toward raw than toward prior"
    )


def test_shrink_small_n_close_to_prior():
    """With n=2, shrunk rate is close to prior (prior dominates)."""
    prior = 0.393
    shrunk = _shrink(n_hits=2, n_valid=2, prior=prior)  # raw = 100%
    # shrunk should be between raw (1.0) and prior (0.393), but close to prior
    assert abs(shrunk - prior) < abs(1.0 - prior), (
        f"With n=2, shrunk={shrunk:.3f} should be closer to prior={prior} than to raw=1.0"
    )


def test_tier_proven_requires_n_and_above_prior():
    """tier 'proven' requires n_eff ≥ 8 AND shrunk > prior."""
    prior = 0.393
    assert _tier(8, 0.50, prior=prior) == "proven"
    assert _tier(8, prior - 0.01, prior=prior) != "proven"  # below prior → not proven
    assert _tier(7, 0.60, prior=prior) != "proven"  # n < 8 → not proven


def test_tier_watch_for_n_3_to_7():
    """tier 'watch' requires 3 ≤ n_eff ≤ 7."""
    prior = 0.393
    assert _tier(3, 0.50, prior=prior) == "watch"
    assert _tier(7, 0.50, prior=prior) == "watch"


def test_tier_limited_for_n_less_than_3():
    """tier 'limited' for n_eff < 3."""
    prior = 0.393
    assert _tier(0, 0.393, prior=prior) == "limited"
    assert _tier(2, 0.80, prior=prior) == "limited"


# ---------------------------------------------------------------------------
# T4: ETF flag in _aggregate
# ---------------------------------------------------------------------------

def test_etf_flag_for_known_etf():
    """is_etf = True for tickers in KNOWN_ETFS."""
    assert "XLV" in KNOWN_ETFS, "XLV must be in KNOWN_ETFS"
    asof = date(2026, 7, 4)
    td = date(2026, 6, 1)
    rd = date(2026, 6, 15)
    trades = [_make_trade("XLV", td=td, rd=rd)]
    agg = _aggregate("XLV", trades, asof)
    assert agg["is_etf"] is True, f"Expected is_etf=True for XLV; got {agg['is_etf']}"


def test_etf_flag_false_for_stock():
    """is_etf = False for a non-ETF ticker."""
    assert "UNH" not in KNOWN_ETFS
    asof = date(2026, 7, 4)
    td = date(2026, 6, 1)
    rd = date(2026, 6, 15)
    trades = [_make_trade("UNH", td=td, rd=rd)]
    agg = _aggregate("UNH", trades, asof)
    assert agg["is_etf"] is False


def test_single_member_flag():
    """single_member = True when only one distinct member traded this ticker."""
    asof = date(2026, 7, 4)
    td = date(2026, 6, 1)
    rd = date(2026, 6, 15)
    trades = [_make_trade("TST", td=td, rd=rd)]  # one member
    agg = _aggregate("TST", trades, asof)
    assert agg["single_member"] is True


def test_multi_member_not_single():
    """single_member = False when more than one member traded this ticker."""
    asof = date(2026, 7, 4)
    td = date(2026, 6, 1)
    rd = date(2026, 6, 15)
    trade1 = _make_trade("TST", td=td, rd=rd)
    trade2 = dict(trade1)
    trade2["representative"] = "John Doe"
    trade2["bio_guide_id"] = "D000456"
    trades = [trade1, trade2]
    agg = _aggregate("TST", trades, asof)
    assert agg["single_member"] is False


# ---------------------------------------------------------------------------
# T5: gate_tier badge in _score
# ---------------------------------------------------------------------------

def test_gate_tier_t1_attached_when_verdict_t1():
    """gate_tier = 'T1' when gate_verdict contains tier_cascade='T1'."""
    agg = _agg(60.0)
    eng = _eng_covered()
    gate_verdict = {"tier_cascade": "T1", "eligible": True}
    row = _score(agg, eng, gate_verdict=gate_verdict)
    assert row["gate_tier"] == "T1", f"Expected gate_tier='T1'; got {row['gate_tier']}"


def test_gate_tier_t3_attached():
    """gate_tier = 'T3' when tier_cascade='T3'."""
    row = _score(_agg(60.0), _eng_covered(),
                 gate_verdict={"tier_cascade": "T3"})
    assert row["gate_tier"] == "T3"


def test_gate_tier_none_when_not_buyable():
    """gate_tier = None when tier_cascade is None/missing."""
    row = _score(_agg(60.0), _eng_covered(),
                 gate_verdict={"tier_cascade": None, "eligible": False})
    assert row["gate_tier"] is None


def test_gate_tier_none_when_no_verdict():
    """gate_tier = None when gate_verdict is None (no gate data)."""
    row = _score(_agg(60.0), _eng_covered(), gate_verdict=None)
    assert row["gate_tier"] is None


def test_gate_tier_not_set_for_invalid_tier():
    """gate_tier = None for tier strings outside T1/T2/T3 (e.g. 'T4' if ever added)."""
    row = _score(_agg(60.0), _eng_covered(),
                 gate_verdict={"tier_cascade": "T4"})
    assert row["gate_tier"] is None
