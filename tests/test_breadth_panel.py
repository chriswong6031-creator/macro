"""Pure-function tests for the market-breadth scorecard (macro dashboard).

Covers the composite participation read, member-weighted aggregation, and the
structural invariants of the live scorecard. No network; the structure test
no-ops gracefully if no breadth parquet is shipped in the checkout.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_site import _breadth_read, _wmean, breadth_scorecard  # noqa: E402


def test_breadth_read_bands():
    # broad: healthy participation AND expanding new highs
    assert _breadth_read(65.0, 120)[2] == "pos"
    assert _breadth_read(60.0, 0)[2] == "pos"            # exactly on the threshold
    # thin: weak participation regardless of highs
    assert _breadth_read(35.0, 50)[2] == "neg"
    # thin: net new LOWS veto an otherwise-okay reading
    assert _breadth_read(58.0, -1)[2] == "neg"
    # mixed: middling pa50, non-negative highs, below the broad bar
    assert _breadth_read(50.0, 5)[2] == "muted"
    assert _breadth_read(59.9, 5)[2] == "muted"
    # graceful: no participation data -> mixed, never raises
    assert _breadth_read(None, 0)[2] == "muted"


def test_breadth_read_is_bilingual():
    label, verdict, _ = _breadth_read(65.0, 120)
    for m in (label, verdict):
        assert 'class="l-en"' in str(m) and 'class="l-zh"' in str(m)


def test_wmean_member_weighted():
    tiers = [{"pa50": 60.0, "n": 100}, {"pa50": 70.0, "n": 300}]
    assert _wmean(tiers, "pa50") == 67.5                 # (60*100 + 70*300)/400
    # missing values are skipped, not treated as zero
    assert _wmean([{"pa50": None, "n": 100}, {"pa50": 80.0, "n": 200}], "pa50") == 80.0
    # all missing -> None (never divide by zero)
    assert _wmean([{"pa50": None, "n": 10}], "pa50") is None


def test_breadth_scorecard_structure():
    d = breadth_scorecard()
    if d is None:        # no breadth data in this checkout — nothing to assert
        return
    comp, tiers = d["comp"], d["tiers"]
    assert 1 <= len(tiers) <= 3
    # composite counts are EXACT sums of the per-tier counts
    assert comp["adv"] == sum(t["adv"] for t in tiers)
    assert comp["dec"] == sum(t["dec"] for t in tiers)
    assert comp["net_nh"] == sum(t["net_nh"] for t in tiers)
    assert comp["n"] == sum(t["n"] for t in tiers)
    # percentages are sane
    for t in tiers:
        assert 0.0 <= t["pa50"] <= 100.0
        assert t["pa200"] is None or 0.0 <= t["pa200"] <= 100.0
        assert t["adv_pct"] is None or 0.0 <= t["adv_pct"] <= 100.0
    assert 0.0 <= comp["pa50"] <= 100.0
    assert comp["tone"] in {"pos", "neg", "muted"}
    assert isinstance(d["asof"], str) and len(d["asof"]) == 10
