"""Tests for build_congress._score — uncovered-row inflation fix (brief #4).

Audit finding: uncovered rows received neutral 50.0 fill-ins for technical and zone,
raising composite by ~30 points and letting them bypass blocked/downtrend multiplier
vetoes.  Fix: composite = W_CLUSTER * cluster only (un-normalised) for uncovered rows;
unconfirmed=True; sort places every unconfirmed row below every covered row.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_congress import _score, W_CLUSTER, W_TECHNICAL, W_ZONE


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
