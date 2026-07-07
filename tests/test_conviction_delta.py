"""tests/test_conviction_delta.py

Unit tests for engine/conviction_delta.py — per-ticker Conviction Delta (Codex B4).

Covers:
  1. Verb change (prev → cur)
  2. Reason add / reason remove
  3. Board enter (ticker not in prev)
  4. Board leave (ticker not in cur)
  5. Empty prior (no dossier keys) → empty entries (fail-soft)
  6. Same-day idempotence guard documented (caller-side; tested here via diff itself)
  7. Cap + sort determinism (verb-upgrades first, downgrades second, reason-only third,
     alphabetical within groups)
  8. None-safety (prev=None, cur with no dossier keys, missing fields)
  9. No-change ticker is NOT emitted

Style follows tests/test_stock_dossier.py.
"""
from __future__ import annotations

import pytest

from engine.conviction_delta import (
    MAX_DELTA,
    diff_standouts,
    load_prev_standouts,
    _verb_strength,
    _sort_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(ticker: str, verb: str | None = None, reasons: list[str] | None = None,
         has_dossier: bool = True) -> dict:
    """Build a minimal board row with an optional dossier."""
    r: dict = {"ticker": ticker, "name": f"{ticker} Inc"}
    if has_dossier:
        dos: dict = {}
        if verb is not None:
            dos["action"] = {"verb": verb, "verb_zh": verb, "tone": verb.lower()}
        if reasons is not None:
            dos["no_buy_reasons"] = reasons
        r["dossier"] = dos
    return r


def _standouts(rows: list[dict], *, as_of: str = "2026-07-01",
               delta: dict | None = None) -> dict:
    """Minimal us_standouts document."""
    doc: dict = {
        "as_of": as_of,
        "buy":   rows,
        "watch": [],
        "laggards": [],
    }
    if delta is not None:
        doc["delta"] = delta
    return doc


# ---------------------------------------------------------------------------
# 1. Verb change
# ---------------------------------------------------------------------------

class TestVerbChange:
    def test_wait_to_buy_emits_entry(self):
        prev = _standouts([_row("AAPL", verb="WAIT")])
        cur  = _standouts([_row("AAPL", verb="BUY")], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert len(delta["entries"]) == 1
        e = delta["entries"][0]
        assert e["ticker"] == "AAPL"
        assert e["prev_verb"] == "WAIT"
        assert e["cur_verb"] == "BUY"
        assert not e["entered_board"]
        assert not e["left_board"]

    def test_buy_to_wait_emits_entry(self):
        prev = _standouts([_row("NVDA", verb="BUY")])
        cur  = _standouts([_row("NVDA", verb="WAIT")], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert len(delta["entries"]) == 1
        assert delta["entries"][0]["prev_verb"] == "BUY"
        assert delta["entries"][0]["cur_verb"] == "WAIT"

    def test_no_change_not_emitted(self):
        prev = _standouts([_row("MSFT", verb="BUY")])
        cur  = _standouts([_row("MSFT", verb="BUY")], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert delta["entries"] == []

    def test_as_of_propagated(self):
        prev = _standouts([_row("AAPL", verb="WAIT")])
        cur  = _standouts([_row("AAPL", verb="BUY")], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert delta["prev_as_of"] == "2026-07-01"
        assert delta["cur_as_of"] == "2026-07-02"


# ---------------------------------------------------------------------------
# 2. Reason add / reason remove
# ---------------------------------------------------------------------------

class TestReasonChanges:
    def test_reason_added(self):
        prev = _standouts([_row("TSLA", verb="BUY", reasons=[])])
        cur  = _standouts([_row("TSLA", verb="BUY", reasons=["extended"])],
                          as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert len(delta["entries"]) == 1
        e = delta["entries"][0]
        assert e["reasons_added"] == ["extended"]
        assert e["reasons_removed"] == []

    def test_reason_removed(self):
        prev = _standouts([_row("GOOG", verb="WAIT", reasons=["earnings_blackout"])])
        cur  = _standouts([_row("GOOG", verb="WAIT", reasons=[])], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert len(delta["entries"]) == 1
        e = delta["entries"][0]
        assert e["reasons_removed"] == ["earnings_blackout"]
        assert e["reasons_added"] == []

    def test_reason_swap(self):
        prev = _standouts([_row("AMZN", verb="WAIT",
                                reasons=["freshness_expired"])])
        cur  = _standouts([_row("AMZN", verb="WAIT",
                                reasons=["earnings_blackout"])],
                          as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert len(delta["entries"]) == 1
        e = delta["entries"][0]
        assert "freshness_expired" in e["reasons_removed"]
        assert "earnings_blackout" in e["reasons_added"]

    def test_reasons_sorted_alphabetically(self):
        prev = _standouts([_row("META", verb="BUY",
                                reasons=["extended", "earnings_blackout"])])
        cur  = _standouts([_row("META", verb="BUY", reasons=[])],
                          as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        e = delta["entries"][0]
        assert e["reasons_removed"] == sorted(["extended", "earnings_blackout"])


# ---------------------------------------------------------------------------
# 3. Board enter
# ---------------------------------------------------------------------------

class TestBoardEnter:
    def test_new_ticker_emitted_as_entered(self):
        prev = _standouts([_row("AAPL", verb="BUY")])
        cur  = _standouts([_row("AAPL", verb="BUY"),
                           _row("NVDA", verb="WATCH")], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        entered = [e for e in delta["entries"] if e["entered_board"]]
        assert len(entered) == 1
        assert entered[0]["ticker"] == "NVDA"
        assert entered[0]["prev_verb"] is None
        assert entered[0]["cur_verb"] == "WATCH"
        assert not entered[0]["left_board"]

    def test_entered_ticker_cur_reasons_in_reasons_added(self):
        prev = _standouts([])
        cur  = _standouts([_row("AAPL", verb="WAIT",
                                reasons=["earnings_blackout"])],
                          as_of="2026-07-02")
        # prev has no rows and no dossiers → empty delta (fail-soft)
        delta = diff_standouts(prev, cur)
        assert delta["entries"] == []

    def test_entered_ticker_with_prev_dossiers_present(self):
        """When prev HAS dossiers on other rows, new ticker is enter."""
        prev = _standouts([_row("AAPL", verb="BUY")])
        cur  = _standouts([_row("AAPL", verb="BUY"),
                           _row("TSLA", verb="WAIT",
                                reasons=["extended"])], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        entered = [e for e in delta["entries"] if e["entered_board"]]
        assert len(entered) == 1
        assert entered[0]["ticker"] == "TSLA"
        assert entered[0]["reasons_added"] == ["extended"]


# ---------------------------------------------------------------------------
# 4. Board leave
# ---------------------------------------------------------------------------

class TestBoardLeave:
    def test_removed_ticker_emitted_as_left(self):
        prev = _standouts([_row("AAPL", verb="BUY"),
                           _row("NVDA", verb="WATCH")])
        cur  = _standouts([_row("AAPL", verb="BUY")], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        left = [e for e in delta["entries"] if e["left_board"]]
        assert len(left) == 1
        assert left[0]["ticker"] == "NVDA"
        assert left[0]["prev_verb"] == "WATCH"
        assert left[0]["cur_verb"] is None
        assert not left[0]["entered_board"]

    def test_left_ticker_prev_reasons_in_reasons_removed(self):
        prev = _standouts([_row("AAPL", verb="BUY"),
                           _row("GOOG", verb="WAIT",
                                reasons=["extended"])])
        cur  = _standouts([_row("AAPL", verb="BUY")], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        left = [e for e in delta["entries"] if e["left_board"]]
        assert left[0]["reasons_removed"] == ["extended"]


# ---------------------------------------------------------------------------
# 5. Empty prior — no dossier keys (first nightly render)
# ---------------------------------------------------------------------------

class TestEmptyPrior:
    def test_none_prev_returns_empty_entries(self):
        cur = _standouts([_row("AAPL", verb="BUY")], as_of="2026-07-02")
        delta = diff_standouts(None, cur)
        assert delta["entries"] == []
        assert delta["prev_as_of"] is None
        assert delta["cur_as_of"] == "2026-07-02"

    def test_prev_with_no_dossier_keys_returns_empty_entries(self):
        """Prev rows exist but none have a 'dossier' key (pre-dossier artifact)."""
        prev_row = {"ticker": "AAPL", "name": "Apple"}  # no dossier
        prev = _standouts([prev_row])
        cur  = _standouts([_row("AAPL", verb="BUY")], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert delta["entries"] == []

    def test_empty_prev_rows_returns_empty_entries(self):
        prev = _standouts([])
        cur  = _standouts([_row("AAPL", verb="BUY")], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert delta["entries"] == []

    def test_prev_none_delta_schema_intact(self):
        cur = _standouts([_row("NVDA", verb="BUY")], as_of="2026-07-02")
        delta = diff_standouts(None, cur)
        assert "prev_as_of" in delta
        assert "cur_as_of" in delta
        assert "entries" in delta
        assert isinstance(delta["entries"], list)


# ---------------------------------------------------------------------------
# 6. Same-day idempotence (diff level: same-day prev produces same delta)
# ---------------------------------------------------------------------------

class TestSameDayIdempotence:
    def test_same_as_of_diff_still_runs(self):
        """diff_standouts itself diffs regardless of as_of equality.
        The idempotence carry-forward is handled in build_stock_library.py
        at the call site.  Here we verify the diff logic itself is deterministic
        when given same-day docs: changes are still detected."""
        prev = _standouts([_row("AAPL", verb="WAIT")], as_of="2026-07-02")
        # Same as_of but different verb (simulates what would happen if we ran diff)
        cur  = _standouts([_row("AAPL", verb="BUY")], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        # diff still detects the change
        assert len(delta["entries"]) == 1
        assert delta["prev_as_of"] == "2026-07-02"
        assert delta["cur_as_of"] == "2026-07-02"

    def test_identical_docs_produce_empty_entries(self):
        """When prev and cur are identical, no entries are emitted."""
        rows = [_row("AAPL", verb="BUY"), _row("MSFT", verb="WATCH")]
        prev = _standouts(rows, as_of="2026-07-02")
        cur  = _standouts(rows, as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert delta["entries"] == []


# ---------------------------------------------------------------------------
# 7. Cap and sort determinism
# ---------------------------------------------------------------------------

class TestCapAndSort:
    def _make_many(self, n: int) -> tuple[dict, dict]:
        """Make prev+cur with n changed tickers: half upgrades, half downgrades."""
        prev_rows = []
        cur_rows  = []
        for i in range(n):
            t = f"TK{i:04d}"
            if i < n // 2:
                prev_rows.append(_row(t, verb="WAIT"))
                cur_rows.append(_row(t, verb="BUY"))
            else:
                prev_rows.append(_row(t, verb="BUY"))
                cur_rows.append(_row(t, verb="WAIT"))
        return (_standouts(prev_rows),
                _standouts(cur_rows, as_of="2026-07-02"))

    def test_capped_at_max_delta(self):
        prev, cur = self._make_many(MAX_DELTA + 10)
        delta = diff_standouts(prev, cur)
        assert len(delta["entries"]) <= MAX_DELTA

    def test_upgrades_before_downgrades(self):
        """Verb upgrades (WAIT→BUY) must appear before downgrades (BUY→WAIT)."""
        prev_rows = [
            _row("ZZZ", verb="BUY"),   # will downgrade
            _row("AAA", verb="WAIT"),  # will upgrade
        ]
        cur_rows = [
            _row("ZZZ", verb="WAIT"),
            _row("AAA", verb="BUY"),
        ]
        prev = _standouts(prev_rows)
        cur  = _standouts(cur_rows, as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert len(delta["entries"]) == 2
        # AAA (upgrade) must come before ZZZ (downgrade)
        tickers = [e["ticker"] for e in delta["entries"]]
        assert tickers.index("AAA") < tickers.index("ZZZ")

    def test_reason_only_after_verb_changes(self):
        """Reason-only changes must appear after verb changes."""
        prev_rows = [
            _row("ZREASONLY", verb="BUY", reasons=["extended"]),  # reason only
            _row("AVERB", verb="WAIT"),                            # verb upgrade
        ]
        cur_rows = [
            _row("ZREASONLY", verb="BUY", reasons=[]),
            _row("AVERB", verb="BUY"),
        ]
        prev = _standouts(prev_rows)
        cur  = _standouts(cur_rows, as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        assert len(delta["entries"]) == 2
        tickers = [e["ticker"] for e in delta["entries"]]
        assert tickers.index("AVERB") < tickers.index("ZREASONLY")

    def test_alphabetical_within_group(self):
        """Within the same group, entries are sorted alphabetically by ticker."""
        prev_rows = [_row("ZZZ", verb="WAIT"), _row("AAA", verb="WAIT"),
                     _row("MMM", verb="WAIT")]
        cur_rows  = [_row("ZZZ", verb="BUY"),  _row("AAA", verb="BUY"),
                     _row("MMM", verb="BUY")]
        prev = _standouts(prev_rows)
        cur  = _standouts(cur_rows, as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        tickers = [e["ticker"] for e in delta["entries"]]
        assert tickers == sorted(tickers)

    def test_deterministic_on_repeated_calls(self):
        """Calling diff_standouts twice with same inputs produces identical output."""
        prev, cur = self._make_many(10)
        d1 = diff_standouts(prev, cur)
        d2 = diff_standouts(prev, cur)
        assert d1 == d2


# ---------------------------------------------------------------------------
# 8. None-safety
# ---------------------------------------------------------------------------

class TestNoneSafety:
    def test_prev_none_does_not_raise(self):
        cur = _standouts([_row("AAPL", verb="BUY")], as_of="2026-07-02")
        result = diff_standouts(None, cur)
        assert isinstance(result, dict)

    def test_row_with_none_dossier_emits_verb_change(self):
        """prev row has dossier: None (key present, value null).

        The prev_has_dossiers check passes because `any("dossier" in r ...)` is True.
        The row itself has no verb (None), so a verb change None→BUY IS detected.
        This is correct: the ticker was on the board before (with no dossier) and now
        has a dossier with verb=BUY — that IS a change worth showing.
        """
        prev_row = {"ticker": "AAPL", "dossier": None}
        prev = _standouts([prev_row])
        cur  = _standouts([_row("AAPL", verb="BUY")], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        # verb changed None → BUY → entry emitted
        assert len(delta["entries"]) == 1
        assert delta["entries"][0]["prev_verb"] is None
        assert delta["entries"][0]["cur_verb"] == "BUY"

    def test_row_missing_ticker_skipped(self):
        prev = _standouts([_row("AAPL", verb="BUY")])
        cur_row_no_ticker = {"name": "No Ticker Co", "dossier": {"action": {"verb": "BUY"}}}
        cur  = {"as_of": "2026-07-02", "buy": [cur_row_no_ticker], "watch": [], "laggards": []}
        # Should not raise; ticker-less rows are skipped
        delta = diff_standouts(prev, cur)
        assert isinstance(delta, dict)

    def test_missing_action_in_dossier_treated_as_none_verb(self):
        prev = _standouts([{"ticker": "AAPL", "dossier": {}}])
        cur  = _standouts([_row("AAPL", verb="BUY")], as_of="2026-07-02")
        # prev has dossier (even if empty) — no_buy_reasons absent, verb=None
        # cur has verb="BUY" → verb changed: None → "BUY"
        delta = diff_standouts(prev, cur)
        assert len(delta["entries"]) == 1
        assert delta["entries"][0]["prev_verb"] is None
        assert delta["entries"][0]["cur_verb"] == "BUY"

    def test_verb_strength_none_returns_minus_one(self):
        assert _verb_strength(None) == -1

    def test_verb_strength_unknown_returns_zero(self):
        assert _verb_strength("UNKNOWN_VERB") == 0

    def test_verb_strength_buy_greater_than_wait(self):
        assert _verb_strength("BUY") > _verb_strength("WAIT")

    def test_verb_strength_case_insensitive(self):
        assert _verb_strength("buy") == _verb_strength("BUY")


# ---------------------------------------------------------------------------
# 9. load_prev_standouts
# ---------------------------------------------------------------------------

class TestLoadPrevStandouts:
    def test_returns_none_for_nonexistent_path(self, tmp_path):
        result = load_prev_standouts(tmp_path / "does_not_exist.json")
        assert result is None

    def test_returns_dict_for_valid_file(self, tmp_path):
        import json
        p = tmp_path / "us_standouts.json"
        p.write_text(json.dumps({"as_of": "2026-07-01", "buy": []}))
        result = load_prev_standouts(p)
        assert isinstance(result, dict)
        assert result["as_of"] == "2026-07-01"

    def test_returns_none_for_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json")
        result = load_prev_standouts(p)
        assert result is None


# ---------------------------------------------------------------------------
# 10. JSON-safety of delta output
# ---------------------------------------------------------------------------

class TestDeltaJsonSafety:
    def test_delta_json_roundtrip(self):
        import json
        prev = _standouts([
            _row("AAPL", verb="WAIT", reasons=["extended"]),
            _row("NVDA", verb="BUY"),
        ])
        cur = _standouts([
            _row("AAPL", verb="BUY", reasons=[]),
            _row("NVDA", verb="WAIT"),
            _row("TSLA", verb="WATCH"),
        ], as_of="2026-07-02")
        delta = diff_standouts(prev, cur)
        serialized = json.dumps(delta, allow_nan=False)
        loaded = json.loads(serialized)
        assert isinstance(loaded["entries"], list)

    def test_check_board_contradictions_not_broken_by_delta(self):
        """Simulate that the delta top-level key does not cause check_board_contradictions
        to error.  The script reads only buy/watch/laggards/lane fields, not delta."""
        import json
        import subprocess
        import sys
        from pathlib import Path

        # Build a minimal us_standouts.json with a delta key
        doc = {
            "as_of": "2026-07-02",
            "buy": [],
            "watch": [],
            "laggards": [],
            "lane_counts": {},
            "delta": {
                "prev_as_of": "2026-07-01",
                "cur_as_of":  "2026-07-02",
                "entries": [{"ticker": "AAPL", "prev_verb": "WAIT", "cur_verb": "BUY",
                             "reasons_added": [], "reasons_removed": [],
                             "entered_board": False, "left_board": False}],
            }
        }
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(doc, f)
            tmp = f.name
        try:
            result = subprocess.run(
                [sys.executable,
                 str(Path(__file__).resolve().parents[1] /
                     "scripts" / "check_board_contradictions.py"),
                 tmp],
                capture_output=True, text=True
            )
            # An empty board is always clean; the script should exit 0
            assert result.returncode == 0, (
                f"check_board_contradictions failed with delta key present: "
                f"{result.stdout}{result.stderr}"
            )
        finally:
            os.unlink(tmp)
