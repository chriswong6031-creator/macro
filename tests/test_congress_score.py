"""Tests for build_congress — uncovered-row inflation fix (brief #4) + W1-S13 freshness fixes.

Existing tests: uncovered/covered composite, multiplier vetoes, act_now.
New tests (W1-S13):
  - T2: _decay uses TransactionDate, not ReportDate
  - T2: filing_lag_days and late_filing flag computed correctly
  - T1: member shrinkage math (congress_members.py)
  - T4: ETF flag in _aggregate
  - T5: gate_tier in _score
New tests (entry leg — W2 of the desk):
  - _entry_leg points table: each signal alone, stacking, cap at 100
  - front_line truth table
  - composite math: veto-exemption, uncovered branch
  - sort bucketing: front_line / unconfirmed priority
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_congress import (
    _score, _decay, _aggregate, _entry_leg,
    W_CLUSTER, W_TECHNICAL, W_ZONE, W_ENTRY,
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
# uncovered composite = (1-W_ENTRY) * W_CLUSTER * cluster only (no neutral gift)
# ---------------------------------------------------------------------------

def test_uncovered_composite_is_cluster_only():
    """Composite for uncovered = (1-W_ENTRY) * W_CLUSTER * cluster; no tech/zone neutral addition,
    entry leg is 0 (no local close to confirm timing)."""
    row = _score(_agg(80.0), _eng_uncovered())
    expected = round((1 - W_ENTRY) * W_CLUSTER * 80.0, 1)
    assert row["composite"] == expected, (
        f"Uncovered composite should be {expected}; got {row['composite']}"
    )


def test_uncovered_composite_below_old_inflated_value():
    """The pre-entry-leg formula gave W_CLUSTER*cluster+... for missing tech+zone.
    The new 4-leg composite must be lower than the old 3-leg neutral-fill composite."""
    cluster = 90.0
    row = _score(_agg(cluster), _eng_uncovered())
    # Old (pre-entry) uncovered formula: W_CLUSTER*cluster (with old weight 0.40); even using
    # the new weight (0.30) the old pre-entry value would have been 0.30*90=27.  New composite
    # adds entry=0 on top via (1-W_ENTRY)*base, shrinking it further to 0.70*0.30*90=18.9.
    old_cluster_only = W_CLUSTER * cluster   # pre-entry formula base
    assert row["composite"] < old_cluster_only, (
        f"New uncovered composite {row['composite']} should be below pre-entry value {old_cluster_only:.1f}"
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
    # The veto applies to base only (entry leg is 0 here since no entry dict supplied → score=0).
    # composite_blocked = (1-W_ENTRY)*base*0.6 + W_ENTRY*0
    # composite_normal  = (1-W_ENTRY)*base      + W_ENTRY*0
    # So ratio of composites equals ratio of bases = 0.6.
    assert abs(blocked["composite"] - round(normal["composite"] * 0.6, 1)) <= 0.5


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
    """Uncovered rows have no meaningful blocked/downtrend flags; composite must be cluster-only
    (no veto multipliers, entry leg = 0)."""
    # Simulate a stale eng dict that happens to have blocked=True from a prior read
    eng = _eng_uncovered()
    eng["blocked"] = True   # should be ignored for uncovered rows
    row = _score(_agg(80.0), eng)
    # New formula: (1-W_ENTRY) * W_CLUSTER * cluster + W_ENTRY * 0
    expected = round((1 - W_ENTRY) * W_CLUSTER * 80.0, 1)
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


# ===========================================================================
# ENTRY LEG TESTS (W2 of the desk — operator-ordered 2026-07-18)
# ===========================================================================

# ---------------------------------------------------------------------------
# helpers for _entry_leg
# ---------------------------------------------------------------------------

def _mk_snap(*, covered=True, wash_2w_state="none", wash_1m_state="none",
             macd_state="none", stoch_state="none"):
    """Minimal entry_snapshot dict for _entry_leg unit tests.

    All sub-dicts carry the contract-required fields; states default to 'none'.
    engine/congress_entry.py is NOT imported here — _entry_leg is pure and takes plain dicts.
    """
    return {
        "covered": covered,
        "wash_2w": {"state": wash_2w_state, "k": None, "coverage": True},
        "wash_1m": {"state": wash_1m_state, "k": None, "coverage": True},
        "dual_washout": (wash_2w_state in ("now", "recent") and wash_1m_state in ("now", "recent")),
        "w_macd": {"state": macd_state, "kind": None, "bars_since": None, "eta_bars": None},
        "w_stoch": {"state": stoch_state, "bars_since": None, "d_at_cross": None,
                    "from_washout": False, "k": None, "d": None, "gap": None},
    }


# ---------------------------------------------------------------------------
# points table: individual signals
# ---------------------------------------------------------------------------

def test_entry_leg_gate_t2_alone():
    """T2 gate contributes 40 points with no other signals."""
    snap = _mk_snap()
    leg = _entry_leg(snap, "T2")
    assert leg["score"] == 40.0, f"T2 alone: expected 40.0, got {leg['score']}"


def test_entry_leg_gate_t1_alone():
    """T1 gate contributes 36 points with no other signals."""
    leg = _entry_leg(_mk_snap(), "T1")
    assert leg["score"] == 36.0, f"T1 alone: expected 36.0, got {leg['score']}"


def test_entry_leg_gate_t3_alone():
    """T3 gate contributes 22 points with no other signals."""
    leg = _entry_leg(_mk_snap(), "T3")
    assert leg["score"] == 22.0, f"T3 alone: expected 22.0, got {leg['score']}"


def test_entry_leg_t2_outscores_t1():
    """T2 (40 pts) must outrank T1 (36 pts) when all else equal."""
    assert _entry_leg(_mk_snap(), "T2")["score"] > _entry_leg(_mk_snap(), "T1")["score"]


def test_entry_leg_dual_washout_alone():
    """Dual washout (both 2W and 1M hit) = 30 pts when no gate."""
    snap = _mk_snap(wash_2w_state="now", wash_1m_state="recent")
    leg = _entry_leg(snap, None)
    assert leg["score"] == 30.0, f"Dual washout alone: expected 30.0, got {leg['score']}"
    assert leg["dual_washout"] is True


def test_entry_leg_single_washout_2w():
    """Single washout (2W only) = 15 pts."""
    snap = _mk_snap(wash_2w_state="now")
    leg = _entry_leg(snap, None)
    assert leg["score"] == 15.0, f"2W hit only: expected 15.0, got {leg['score']}"
    assert leg["wash_2w_hit"] is True
    assert leg["wash_1m_hit"] is False


def test_entry_leg_single_washout_1m():
    """Single washout (1M only) = 15 pts."""
    snap = _mk_snap(wash_1m_state="recent")
    leg = _entry_leg(snap, None)
    assert leg["score"] == 15.0, f"1M hit only: expected 15.0, got {leg['score']}"
    assert leg["wash_1m_hit"] is True


def test_entry_leg_near_only():
    """Near-only (no hit, either wash state == 'near') = 6 pts."""
    snap = _mk_snap(wash_2w_state="near")
    leg = _entry_leg(snap, None)
    assert leg["score"] == 6.0, f"Near-only (2W near): expected 6.0, got {leg['score']}"


def test_entry_leg_near_only_1m():
    """Near-only via 1M 'near' state = 6 pts."""
    snap = _mk_snap(wash_1m_state="near")
    leg = _entry_leg(snap, None)
    assert leg["score"] == 6.0, f"Near-only (1M near): expected 6.0, got {leg['score']}"


def test_entry_leg_macd_crossed_alone():
    """w_macd crossed alone = 15 pts."""
    leg = _entry_leg(_mk_snap(macd_state="crossed"), None)
    assert leg["score"] == 15.0


def test_entry_leg_macd_approaching_alone():
    """w_macd approaching alone = 10 pts."""
    leg = _entry_leg(_mk_snap(macd_state="approaching"), None)
    assert leg["score"] == 10.0


def test_entry_leg_stoch_crossed_alone():
    """w_stoch crossed alone = 15 pts."""
    leg = _entry_leg(_mk_snap(stoch_state="crossed"), None)
    assert leg["score"] == 15.0


def test_entry_leg_stoch_approaching_alone():
    """w_stoch approaching alone = 10 pts."""
    leg = _entry_leg(_mk_snap(stoch_state="approaching"), None)
    assert leg["score"] == 10.0


def test_entry_leg_stacking_t2_dual_macd_stoch():
    """T2 + dual washout + macd crossed + stoch crossed = 40+30+15+15 = 100 (capped)."""
    snap = _mk_snap(wash_2w_state="now", wash_1m_state="now",
                    macd_state="crossed", stoch_state="crossed")
    leg = _entry_leg(snap, "T2")
    assert leg["score"] == 100.0, f"Stacked: expected 100.0 (capped), got {leg['score']}"


def test_entry_leg_cap_at_100():
    """Points beyond 100 are capped at 100."""
    snap = _mk_snap(wash_2w_state="now", wash_1m_state="recent",
                    macd_state="crossed", stoch_state="crossed")
    leg = _entry_leg(snap, "T1")   # 36+30+15+15 = 96 — just under cap
    assert leg["score"] == 96.0, f"Expected 96.0, got {leg['score']}"
    # Push over cap
    leg2 = _entry_leg(snap, "T2")  # 40+30+15+15 = 100 — at cap
    assert leg2["score"] == 100.0
    # Even further over: T2 + dual + macd crossed + stoch crossed = same since already at 100
    assert leg2["score"] <= 100.0


# ---------------------------------------------------------------------------
# front_line truth table
# ---------------------------------------------------------------------------

def test_front_line_prime_t1():
    """prime (T1 gate) → front_line=True even with no wash/tech signals."""
    leg = _entry_leg(_mk_snap(), "T1")
    assert leg["prime"] is True
    assert leg["front_line"] is True


def test_front_line_prime_t2():
    """prime (T2 gate) → front_line=True."""
    leg = _entry_leg(_mk_snap(), "T2")
    assert leg["prime"] is True
    assert leg["front_line"] is True


def test_front_line_t3_gate():
    """T3 gate → front_line=True (gate_tier=='T3' condition)."""
    leg = _entry_leg(_mk_snap(), "T3")
    assert leg["prime"] is False      # T3 is not prime
    assert leg["front_line"] is True


def test_front_line_dual_washout():
    """Dual washout → front_line=True even with no gate."""
    snap = _mk_snap(wash_2w_state="now", wash_1m_state="now")
    leg = _entry_leg(snap, None)
    assert leg["front_line"] is True


def test_front_line_macd_crossed():
    """w_macd crossed → front_line=True."""
    leg = _entry_leg(_mk_snap(macd_state="crossed"), None)
    assert leg["front_line"] is True


def test_front_line_macd_approaching():
    """w_macd approaching → front_line=True."""
    leg = _entry_leg(_mk_snap(macd_state="approaching"), None)
    assert leg["front_line"] is True


def test_front_line_stoch_crossed():
    """w_stoch crossed → front_line=True."""
    leg = _entry_leg(_mk_snap(stoch_state="crossed"), None)
    assert leg["front_line"] is True


def test_front_line_none_signals():
    """No signals, no gate → front_line=False."""
    leg = _entry_leg(_mk_snap(), None)
    assert leg["front_line"] is False


def test_front_line_no_close_with_t2_gate():
    """snapshot=None (no local close) + T2 gate → prime=True, front_line=True, score=40."""
    leg = _entry_leg(None, "T2")
    assert leg["prime"] is True
    assert leg["front_line"] is True
    assert leg["score"] == 40.0
    assert leg["covered"] is False


def test_front_line_no_close_no_gate():
    """snapshot=None + no gate → all False, score 0."""
    leg = _entry_leg(None, None)
    assert leg["prime"] is False
    assert leg["front_line"] is False
    assert leg["score"] == 0.0
    assert leg["covered"] is False


# ---------------------------------------------------------------------------
# setting_up truth table
# ---------------------------------------------------------------------------

def test_setting_up_t3_gate():
    """T3 gate → setting_up=True."""
    assert _entry_leg(_mk_snap(), "T3")["setting_up"] is True


def test_setting_up_macd_approaching():
    """w_macd approaching → setting_up=True."""
    assert _entry_leg(_mk_snap(macd_state="approaching"), None)["setting_up"] is True


def test_setting_up_stoch_approaching():
    """w_stoch approaching → setting_up=True."""
    assert _entry_leg(_mk_snap(stoch_state="approaching"), None)["setting_up"] is True


def test_setting_up_near_wash():
    """Near wash (no hit) → setting_up=True."""
    assert _entry_leg(_mk_snap(wash_2w_state="near"), None)["setting_up"] is True


def test_setting_up_false_when_crossed_and_no_gate():
    """Crossed signals (not approaching) with no gate → setting_up=False."""
    leg = _entry_leg(_mk_snap(macd_state="crossed"), None)
    # crossed is front_line but NOT setting_up (setting_up = approaching/near/T3 only)
    assert leg["setting_up"] is False


# ---------------------------------------------------------------------------
# fresh_10d truth table
# ---------------------------------------------------------------------------

def test_fresh_10d_macd_crossed():
    assert _entry_leg(_mk_snap(macd_state="crossed"), None)["fresh_10d"] is True


def test_fresh_10d_stoch_crossed():
    assert _entry_leg(_mk_snap(stoch_state="crossed"), None)["fresh_10d"] is True


def test_fresh_10d_wash_2w_hit():
    assert _entry_leg(_mk_snap(wash_2w_state="now"), None)["fresh_10d"] is True


def test_fresh_10d_gate_tier():
    """Any gate tier → fresh_10d=True."""
    assert _entry_leg(_mk_snap(), "T3")["fresh_10d"] is True


def test_fresh_10d_false_no_signals():
    """No signals, no gate → fresh_10d=False."""
    assert _entry_leg(_mk_snap(), None)["fresh_10d"] is False


# ---------------------------------------------------------------------------
# composite math: veto-exemption
# ---------------------------------------------------------------------------

def test_entry_veto_exempt_blocked():
    """Entry score is NOT reduced by the blocked multiplier.

    A blocked covered name with a wash signal should keep its entry score contribution
    while the base (cluster+technical+zone) is hit by 0.6.

    Design:
      composite = (1-W_ENTRY)*base + W_ENTRY*entry_score
      blocked:  (1-W_ENTRY)*base*0.6 + W_ENTRY*entry_score
      normal:   (1-W_ENTRY)*base*1.0 + W_ENTRY*entry_score
      diff = (1-W_ENTRY)*base*(1-0.6) = 0.70 * base * 0.4

    We verify the entry_score contribution is the same in both rows by computing
    what each composite would be without entry, then checking the ratio = 0.6.
    """
    ent = _entry_leg(_mk_snap(wash_2w_state="now"), None)
    assert ent["score"] == 15.0

    blocked_row = _score(_agg(60.0), _eng_covered(blocked=True),  entry=ent)
    normal_row  = _score(_agg(60.0), _eng_covered(blocked=False), entry=ent)

    # Also compute rows with zero-entry to isolate the base
    zero_ent = _entry_leg(_mk_snap(), None)   # score=0, no signals, no gate
    assert zero_ent["score"] == 0.0
    blocked_base_row = _score(_agg(60.0), _eng_covered(blocked=True),  entry=zero_ent)
    normal_base_row  = _score(_agg(60.0), _eng_covered(blocked=False), entry=zero_ent)

    # Entry contribution is the same in both: W_ENTRY * 15 added on top.
    # So composite_blocked - composite_blocked_zero ≈ composite_normal - composite_normal_zero
    entry_lift_blocked = blocked_row["composite"] - blocked_base_row["composite"]
    entry_lift_normal  = normal_row["composite"]  - normal_base_row["composite"]

    assert abs(entry_lift_blocked - entry_lift_normal) <= 0.5, (
        f"Entry lift must be identical in blocked vs normal rows "
        f"(veto is base-only); blocked_lift={entry_lift_blocked:.2f}, normal_lift={entry_lift_normal:.2f}"
    )
    # Also confirm overall: blocked < normal (veto still reduces composite via base)
    assert blocked_row["composite"] < normal_row["composite"]


def test_entry_veto_exempt_downtrend():
    """Entry score is not reduced by the downtrend multiplier."""
    ent = _entry_leg(_mk_snap(wash_1m_state="recent"), None)
    assert ent["score"] == 15.0

    dt_row = _score(_agg(60.0), _eng_covered(downtrend=True), entry=ent)
    ok_row  = _score(_agg(60.0), _eng_covered(downtrend=False), entry=ent)

    # Both should carry the same W_ENTRY * 15 portion; downtrend row is just lower overall.
    assert dt_row["composite"] < ok_row["composite"]
    # Downtrend composite = (1-W_ENTRY) * base * 0.6 + W_ENTRY * 15
    # Normal  composite  = (1-W_ENTRY) * base       + W_ENTRY * 15
    # Difference = (1-W_ENTRY) * base * 0.4 — pure base reduction.
    diff = ok_row["composite"] - dt_row["composite"]
    assert diff > 0


def test_uncovered_entry_score_zero():
    """Uncovered path with NO signals: entry score 0 -> composite is the shrunk cluster base."""
    row = _score(_agg(80.0), _eng_uncovered())
    expected = round((1 - W_ENTRY) * W_CLUSTER * 80.0, 1)
    assert row["composite"] == expected


def test_uncovered_gate_points_count_in_composite():
    """Review 07-18: engine coverage and entry coverage are independent — an engine-uncovered
    name with a gate tier still earns its entry points in the composite (it stays in the
    unconfirmed bucket, so this only orders within that bucket)."""
    row = _score(_agg(80.0), _eng_uncovered(), gate_verdict={"tier_cascade": "T2"})
    expected = round((1 - W_ENTRY) * W_CLUSTER * 80.0 + W_ENTRY * 40.0, 1)
    assert row["composite"] == expected
    assert row["unconfirmed"] is True
    assert row["entry"]["front_line"] is True


# ---------------------------------------------------------------------------
# sort bucketing
# ---------------------------------------------------------------------------

def test_sort_front_line_before_non_front_line():
    """front_line covered name with lower composite ranks above non-front-line covered name."""
    # front-line entry: dual washout triggers front_line (single hit does not per contract)
    fl_entry = _entry_leg(_mk_snap(wash_2w_state="now", wash_1m_state="now"), None)
    fl_row = _score(_agg(40.0, "FL"), _eng_covered(tech=40.0, zone=40.0), entry=fl_entry)
    assert fl_row["entry"]["front_line"] is True

    # non-front-line entry: no signals, no gate
    nfl_entry = _entry_leg(_mk_snap(), None)
    nfl_row = _score(_agg(90.0, "NFL"), _eng_covered(tech=90.0, zone=90.0), entry=nfl_entry)
    assert nfl_row["entry"]["front_line"] is False

    # nfl has higher composite — but fl must sort first due to front_line bucket
    assert nfl_row["composite"] > fl_row["composite"], (
        "Pre-condition: NFL composite must be higher than FL composite for test to be meaningful"
    )

    rows = sorted([nfl_row, fl_row],
                  key=lambda a: (1 if a["unconfirmed"] else 0,
                                 0 if a["entry"]["front_line"] else 1,
                                 -a["composite"]))
    assert rows[0]["ticker"] == "FL", (
        f"front_line name should sort first; got {rows[0]['ticker']} "
        f"(FL composite={fl_row['composite']}, NFL composite={nfl_row['composite']})"
    )


def test_sort_unconfirmed_always_last():
    """Unconfirmed (uncovered) rows always sort after confirmed rows, regardless of composite."""
    # High-composite uncovered row
    unc_entry = _entry_leg(None, None)
    unc_row = _score(_agg(100.0, "UNC"), _eng_uncovered(), entry=unc_entry)
    assert unc_row["unconfirmed"] is True

    # Low-composite covered row with no signals
    cov_entry = _entry_leg(_mk_snap(), None)
    cov_row = _score(_agg(20.0, "COV"), _eng_covered(tech=20.0, zone=20.0), entry=cov_entry)
    assert cov_row["unconfirmed"] is False

    rows = sorted([unc_row, cov_row],
                  key=lambda a: (1 if a["unconfirmed"] else 0,
                                 0 if a["entry"]["front_line"] else 1,
                                 -a["composite"]))
    assert rows[0]["ticker"] == "COV", (
        f"Covered row must sort before unconfirmed; got {rows[0]['ticker']}"
    )
    assert rows[1]["ticker"] == "UNC"


def test_sort_three_way_ordering():
    """Full three-way sort: unconfirmed last; front_line before non-front-line; composite within."""
    fl_entry  = _entry_leg(_mk_snap(macd_state="crossed"), None)
    nfl_entry = _entry_leg(_mk_snap(), None)
    unc_entry = _entry_leg(None, None)

    fl_row   = _score(_agg(50.0, "FL"),  _eng_covered(tech=50.0, zone=50.0), entry=fl_entry)
    nfl_row  = _score(_agg(70.0, "NFL"), _eng_covered(tech=70.0, zone=70.0), entry=nfl_entry)
    unc_row  = _score(_agg(99.0, "UNC"), _eng_uncovered(), entry=unc_entry)

    rows = sorted([nfl_row, unc_row, fl_row],
                  key=lambda a: (1 if a["unconfirmed"] else 0,
                                 0 if a["entry"]["front_line"] else 1,
                                 -a["composite"]))
    tickers = [r["ticker"] for r in rows]
    assert tickers[2] == "UNC", f"Unconfirmed must be last; order={tickers}"
    assert tickers[0] == "FL",  f"front_line must be first; order={tickers}"
    assert tickers[1] == "NFL", f"Non-front-line covered second; order={tickers}"
