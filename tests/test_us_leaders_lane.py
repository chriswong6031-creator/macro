"""tests/test_us_leaders_lane.py — Leaders strip admission + ordering + NaN safety.

Covers the 2026-07-28 gate-width order: the US board's fresh-cross confluence gate
structurally cannot admit a market leader that never pulls back (measured 2026-07-28:
of the top-100 3-month runners, 2 passed the gate, 53 sat at flat-sell). The leaders
lane is DISPLAY-TIER coverage of those names — never an entry claim.

Tests import the REAL helpers from scripts.build_stock_library (_select_leaders,
LEADERS_CAP, LEADERS_ALPHA_FLOOR, _drop_spurious_sector_rows, _json_safe) — the same
module-import pattern tests/test_us_standouts_cascade_gate.py uses — so nothing here
mirrors builder logic.

Key invariants:
  A. Admission: intact trend (above200 AND weekly_bull, both strictly True) AND
     alpha >= LEADERS_ALPHA_FLOOR AND not already surfaced (exclude) AND dir != 'down'.
  B. Order: alpha desc, ticker asc tiebreak (deterministic — same inputs, same strip).
  C. Dual-class dedup keeps the FIRST-ranked variant; cap caps; rows tag lane='leader'.
  D. Serialisation: leaders rows go through the SAME whole-dict _json_safe scrub the
     artifact write applies, so allow_nan=False cannot trip on a new lane.
"""
from __future__ import annotations

import json
import math

from scripts.build_stock_library import (
    LEADERS_ALPHA_FLOOR,
    LEADERS_CAP,
    _drop_spurious_sector_rows,
    _json_safe,
    _select_leaders,
)

# ---------------------------------------------------------------------------
# Fixtures (data only — all logic under test is imported)
# ---------------------------------------------------------------------------


def _row(ticker: str, alpha, *, name: str | None = None,
         sector: str = "Information Technology", **extra) -> dict:
    """One board row as row_by_t holds it. `name` defaults to a unique company so
    the dual-class dedup is inert unless a test opts in by sharing a name."""
    r = {"ticker": ticker, "name": name if name is not None else f"{ticker} Corp",
         "sector": sector, "alpha": alpha}
    r.update(extra)
    return r


def _verdict(*, above200=True, weekly_bull=True) -> dict:
    """Minimal signal_gate verdict — only the two structure keys the strip gates on."""
    return {"above200": above200, "weekly_bull": weekly_bull, "eligible": False}


def _fixture(rows: list[dict], verdicts: dict | None = None) -> tuple[list, dict, dict]:
    """(scored, row_by_t, sig_verdict) for a list of rows. scored order is irrelevant
    to the strip (it re-sorts by alpha) but is kept ticker-stable for readability."""
    row_by_t = {r["ticker"]: r for r in rows}
    scored = [(r["ticker"], {"composite_z": 0.0}) for r in rows]
    sv = {r["ticker"]: _verdict() for r in rows}
    sv.update(verdicts or {})
    return scored, row_by_t, sv


def _tickers(leaders: list[dict]) -> list[str]:
    return [r["ticker"] for r in leaders]


# ---------------------------------------------------------------------------
# A. Admission
# ---------------------------------------------------------------------------

class TestLeadersAdmission:

    def test_structure_intact_above_floor_admitted(self):
        """The base case: above200 + weekly_bull + alpha >= floor is admitted."""
        scored, rbt, sv = _fixture([_row("NVDA", 1.8)])
        assert _tickers(_select_leaders(scored, rbt, sv, set())) == ["NVDA"]

    def test_alpha_exactly_at_floor_admitted(self):
        """The floor is inclusive (>=), matching the BUY_MIN prior it is based on."""
        scored, rbt, sv = _fixture([_row("EDGE", LEADERS_ALPHA_FLOOR)])
        assert _tickers(_select_leaders(scored, rbt, sv, set())) == ["EDGE"]

    def test_excluded_ticker_dropped(self):
        """A name already surfaced on buy/watch/laggards never repeats on the strip."""
        scored, rbt, sv = _fixture([_row("NVDA", 1.8), _row("AMD", 1.5)])
        out = _select_leaders(scored, rbt, sv, {"NVDA"})
        assert _tickers(out) == ["AMD"]

    def test_above200_false_excluded(self):
        scored, rbt, sv = _fixture(
            [_row("BRKN", 2.0)], {"BRKN": _verdict(above200=False)})
        assert _select_leaders(scored, rbt, sv, set()) == []

    def test_above200_none_excluded(self):
        """None means UNKNOWN, not intact — an unanalysed name is not a leader."""
        scored, rbt, sv = _fixture(
            [_row("UNKN", 2.0)], {"UNKN": _verdict(above200=None)})
        assert _select_leaders(scored, rbt, sv, set()) == []

    def test_weekly_bull_false_excluded(self):
        scored, rbt, sv = _fixture(
            [_row("ROLL", 2.0)], {"ROLL": _verdict(weekly_bull=False)})
        assert _select_leaders(scored, rbt, sv, set()) == []

    def test_weekly_bull_none_excluded(self):
        scored, rbt, sv = _fixture(
            [_row("UNKW", 2.0)], {"UNKW": _verdict(weekly_bull=None)})
        assert _select_leaders(scored, rbt, sv, set()) == []

    def test_missing_verdict_excluded(self):
        """No verdict at all => no structure evidence => not admitted."""
        scored, rbt, _sv = _fixture([_row("GHOST", 2.0)])
        assert _select_leaders(scored, rbt, {}, set()) == []

    def test_alpha_none_excluded(self):
        scored, rbt, sv = _fixture([_row("NOALPHA", None)])
        assert _select_leaders(scored, rbt, sv, set()) == []

    def test_alpha_below_floor_excluded(self):
        scored, rbt, sv = _fixture([_row("WEAK", LEADERS_ALPHA_FLOOR - 0.01)])
        assert _select_leaders(scored, rbt, sv, set()) == []

    def test_alpha_nan_excluded(self):
        """NaN fails the >= comparison — the row must not reach the artifact."""
        scored, rbt, sv = _fixture([_row("NANY", float("nan"))])
        assert _select_leaders(scored, rbt, sv, set()) == []

    def test_dir_down_excluded(self):
        scored, rbt, sv = _fixture([_row("FALL", 2.0, dir="down")])
        assert _select_leaders(scored, rbt, sv, set()) == []

    def test_dir_up_and_absent_admitted(self):
        """dir='up' and a missing dir key are both fine — only 'down' is a veto."""
        scored, rbt, sv = _fixture([_row("UPUP", 2.0, dir="up"), _row("BARE", 1.9)])
        assert _tickers(_select_leaders(scored, rbt, sv, set())) == ["UPUP", "BARE"]

    def test_row_missing_from_row_by_t_skipped(self):
        """A scored ticker with no board row is skipped, not a crash."""
        scored, rbt, sv = _fixture([_row("REAL", 2.0)])
        scored = scored + [("PHANTOM", {"composite_z": 0.0})]
        sv["PHANTOM"] = _verdict()
        assert _tickers(_select_leaders(scored, rbt, sv, set())) == ["REAL"]


# ---------------------------------------------------------------------------
# B. Ordering
# ---------------------------------------------------------------------------

class TestLeadersOrdering:

    def test_alpha_desc(self):
        scored, rbt, sv = _fixture(
            [_row("LOW", 0.6), _row("HIGH", 3.1), _row("MID", 1.4)])
        assert _tickers(_select_leaders(scored, rbt, sv, set())) == ["HIGH", "MID", "LOW"]

    def test_ticker_tiebreak_is_ascending_and_deterministic(self):
        """Equal alpha must never leave order to dict/scored insertion order."""
        scored, rbt, sv = _fixture([_row("ZZZ", 1.0), _row("AAA", 1.0), _row("MMM", 1.0)])
        assert _tickers(_select_leaders(scored, rbt, sv, set())) == ["AAA", "MMM", "ZZZ"]
        # reversed input, identical output
        rows = [_row("MMM", 1.0), _row("AAA", 1.0), _row("ZZZ", 1.0)]
        scored2, rbt2, sv2 = _fixture(rows)
        assert _tickers(_select_leaders(scored2, rbt2, sv2, set())) == ["AAA", "MMM", "ZZZ"]


# ---------------------------------------------------------------------------
# C. Dedup / cap / lane tag
# ---------------------------------------------------------------------------

class TestLeadersDedupCapTag:

    def test_dual_class_dedupe_keeps_first_ranked(self):
        """GOOG/GOOGL share a normalised company name — the higher-alpha variant wins."""
        scored, rbt, sv = _fixture([
            _row("GOOG", 1.2, name="Alphabet Inc"),
            _row("GOOGL", 1.9, name="Alphabet Inc."),
            _row("MSFT", 1.5, name="Microsoft Corp"),
        ])
        assert _tickers(_select_leaders(scored, rbt, sv, set())) == ["GOOGL", "MSFT"]

    def test_cap_respected(self):
        rows = [_row(f"T{i:02d}", 1.0 + i / 100) for i in range(LEADERS_CAP + 7)]
        scored, rbt, sv = _fixture(rows)
        out = _select_leaders(scored, rbt, sv, set())
        assert len(out) == LEADERS_CAP
        # the cap keeps the TOP alpha rows, not an arbitrary slice
        assert out[0]["ticker"] == f"T{LEADERS_CAP + 6:02d}"

    def test_explicit_cap_override(self):
        rows = [_row(f"T{i}", 1.0 + i / 100) for i in range(6)]
        scored, rbt, sv = _fixture(rows)
        assert len(_select_leaders(scored, rbt, sv, set(), cap=2)) == 2

    def test_explicit_floor_override(self):
        scored, rbt, sv = _fixture([_row("SMALL", 0.2)])
        assert _select_leaders(scored, rbt, sv, set()) == []
        assert _tickers(_select_leaders(scored, rbt, sv, set(), floor=0.1)) == ["SMALL"]

    def test_rows_tagged_lane_leader(self):
        """The lane tag is what keeps the strip out of every buy-lane consumer."""
        scored, rbt, sv = _fixture([_row("NVDA", 1.8), _row("AMD", 1.5)])
        out = _select_leaders(scored, rbt, sv, set())
        assert [r["lane"] for r in out] == ["leader", "leader"]

    def test_non_admitted_rows_not_tagged(self):
        """A row that fails admission must not acquire lane='leader' as a side effect."""
        scored, rbt, sv = _fixture(
            [_row("NOPE", 2.0)], {"NOPE": _verdict(above200=False)})
        assert _select_leaders(scored, rbt, sv, set()) == []
        assert "lane" not in rbt["NOPE"]

    def test_empty_inputs_return_empty(self):
        assert _select_leaders([], {}, {}, set()) == []


# ---------------------------------------------------------------------------
# D. Artifact-side safety: the leaders lane is a NEW serialised array
# ---------------------------------------------------------------------------

class TestLeadersArtifactSafety:

    def test_json_safe_scrubs_the_leaders_lane(self):
        """The artifact write is `json.dumps(_json_safe(wide), allow_nan=False)`.
        _json_safe is a WHOLE-DICT recursive scrub, so a new top-level lane is
        covered with no lane-keyed change — this pins that. A non-finite float
        anywhere under leaders[] would otherwise raise ValueError on the write."""
        wide = {"as_of": "2026-07-28", "buy": [], "watch": [],
                "leaders": [{"ticker": "NVDA", "lane": "leader", "alpha": 1.8,
                             "ext_z": float("nan"),
                             "conviction": {"score": float("inf")},
                             "entry_signal": {"buy_zone": {"low": float("nan"),
                                                           "high": 101.0}}}],
                "laggards": []}
        payload = json.dumps(_json_safe(wide), separators=(",", ":"),
                             default=str, allow_nan=False)
        back = json.loads(payload)
        row = back["leaders"][0]
        assert row["ext_z"] is None
        assert row["conviction"]["score"] is None
        assert row["entry_signal"]["buy_zone"]["low"] is None
        assert row["entry_signal"]["buy_zone"]["high"] == 101.0
        assert not any(math.isnan(v) for v in [1.8])  # sanity: finite values survive
        assert row["alpha"] == 1.8

    def test_spurious_sector_guard_sweeps_leaders(self):
        """The sector-integrity backstop must cover the new lane too — a junk sector
        label on a leaders row would otherwise ship straight to the strip."""
        wide = {"buy": [], "watch": [], "laggards": [],
                "leaders": [{"ticker": "GOOD", "sector": "Information Technology"},
                            {"ticker": "BLANK", "sector": None},
                            {"ticker": "JUNK", "sector": "history"}]}
        dropped = _drop_spurious_sector_rows(wide)
        assert [r["ticker"] for r in wide["leaders"]] == ["GOOD", "BLANK"]
        assert dropped["leaders"] == [("JUNK", "history")]

    def test_spurious_sector_guard_tolerates_missing_leaders_key(self):
        """Pre-migration shape (no leaders key) must not raise."""
        wide = {"buy": [{"ticker": "A", "sector": "Energy"}], "watch": [], "laggards": []}
        assert _drop_spurious_sector_rows(wide) == {}
        assert "leaders" not in wide
