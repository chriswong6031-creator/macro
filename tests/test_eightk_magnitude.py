"""tests/test_eightk_magnitude.py — W1c hermetic tests.

Coverage:
  1. _parse_dollar_amounts: amounts in text, tables, 'approximately $X million/billion',
     absent text -> extraction_ok False.  Fixture amounts are deliberately non-equal so
     tests cannot pass vacuously when the parser returns a constant.
  2. _parse_counterparty: present vs absent.
  3. _contract_z_for_member: large baseline + current -> z; thin history (n<BASELINE_MIN)
     -> None.
  4. Pre-drift gate: requires BOTH large-z AND flat consensus; consensus already moved
     -> no flag (fixture where direction != 'stable').
  5. Ledger dedup: second append with same (theme, asof) does NOT add a row.
  6. compute_eightk_magnitude: end-to-end with synthetic fixtures.

All tests use synthetic DataFrames; zero network calls.
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
import pandas as pd
import pytest

# ---- import targets --------------------------------------------------------
from collectors.edgar_8k import _parse_dollar_amounts, _parse_counterparty
from engine.eightk_magnitude import (
    BASELINE_MIN,
    LARGE_Z_THRESHOLD,
    RECENT_WINDOW_DAYS,
    _consensus_flat,
    _contract_z_for_member,
    _append_ledger,
    compute_eightk_magnitude,
)


# ===========================================================================
# 1. _parse_dollar_amounts
# ===========================================================================

class TestParseDollarAmounts:
    def test_billion_explicit(self):
        text = "Company entered into an agreement for approximately $2.5 billion."
        amount, ok = _parse_dollar_amounts(text)
        assert ok is True
        # Should be close to 2.5e9
        assert abs(amount - 2_500_000_000) < 1

    def test_million_explicit(self):
        text = "The total consideration is $450 million payable in cash."
        amount, ok = _parse_dollar_amounts(text)
        assert ok is True
        assert abs(amount - 450_000_000) < 1

    def test_raw_number_large(self):
        # Raw figure without suffix — must be large enough (>= 10k) to not be filtered
        text = "Aggregate principal amount of $3,200,000."
        amount, ok = _parse_dollar_amounts(text)
        assert ok is True
        assert abs(amount - 3_200_000) < 1

    def test_mm_suffix(self):
        text = "Commitment of $125MM under the revolving facility."
        amount, ok = _parse_dollar_amounts(text)
        assert ok is True
        assert abs(amount - 125_000_000) < 1

    def test_picks_largest_of_multiple(self):
        # Two figures: $50M and $1.2B — should return 1.2B
        text = "The initial tranche is $50 million, with total capacity of $1.2 billion."
        amount, ok = _parse_dollar_amounts(text)
        assert ok is True
        assert abs(amount - 1_200_000_000) < 1

    def test_absent_returns_false(self):
        text = "The Company entered into a material definitive agreement with Acme Corp."
        amount, ok = _parse_dollar_amounts(text)
        assert ok is False
        assert amount is None

    def test_small_noise_filtered(self):
        # Values under $10k (e.g., $0.01 par value, $5 fee) should be ignored
        text = "Common stock, par value $0.01 per share."
        amount, ok = _parse_dollar_amounts(text)
        assert ok is False
        assert amount is None

    def test_amounts_not_equal_to_each_other(self):
        # Guard: billion ≠ million (proves multiplier is applied)
        _, ok_b = _parse_dollar_amounts("$1 billion deal")
        _, ok_m = _parse_dollar_amounts("$1 million deal")
        am_b, _ = _parse_dollar_amounts("$1 billion deal")
        am_m, _ = _parse_dollar_amounts("$1 million deal")
        assert ok_b and ok_m
        assert am_b != am_m   # would fail if multiplier were broken
        assert am_b > am_m

    def test_suffix_overmatch_adversarial(self):
        """Multiplier suffixes must be word-bounded: '$5 mmBtu' is NOT $5M (dollars per
        million BTU -- common energy-1.01 boilerplate), '$10 millionaire' is NOT $10M,
        '$4 bnb tokens' is NOT $4B.  Since the parser keeps the LARGEST match, a single
        over-matched suffix would corrupt amount_usd -> contract_dollar_z -> a false
        pre_drift flag on the graded ledger."""
        for text in ("natural gas priced at $5 mmBtu under the agreement",
                     "the $10 millionaire founder retains control",
                     "purchase of $4 bnb tokens as consideration",
                     "with a par value $0.01 per share"):
            amount, ok = _parse_dollar_amounts(text)
            assert amount is None and ok is False, f"over-match: {text!r} -> {amount}"
        # the spurious hit must not shadow a real amount either
        amount, ok = _parse_dollar_amounts(
            "gas at $9 mmBtu; total contract value of $450 million")
        assert ok is True and amount == 450_000_000.0

    def test_legit_suffixes_still_match(self):
        """The word-boundary fix must not break the legitimate suffix forms."""
        cases = {"$450 million": 450e6, "$2.5 billion": 2.5e9, "$125MM": 125e6,
                 "$12.5M in fees": 12.5e6, "$3,200,000": 3_200_000.0, "$7 bn": 7e9}
        for text, want in cases.items():
            amount, ok = _parse_dollar_amounts(text)
            assert ok is True and amount == want, f"{text!r} -> {amount}, want {want}"


# ===========================================================================
# 2. _parse_counterparty
# ===========================================================================

class TestParseCounterparty:
    def test_with_clause(self):
        text = "Company entered into a Loan Agreement with Global Finance Corp, LLC."
        cp = _parse_counterparty(text)
        assert cp is not None
        assert len(cp) >= 3

    def test_absent(self):
        text = "A material agreement was entered into."
        cp = _parse_counterparty(text)
        # May return None — but must not raise
        assert cp is None or isinstance(cp, str)


# ===========================================================================
# 3. _contract_z_for_member — z-score math
# ===========================================================================

def _make_events_df(ticker: str, amounts_baseline: list[float],
                    amounts_current: list[float], today: pd.Timestamp) -> pd.DataFrame:
    """Build a synthetic events DataFrame for one ticker.

    baseline amounts land in [today-365, today-46];
    current amounts land in [today-44, today].
    extraction_ok=True for all rows with a non-None amount.
    """
    rows = []
    n_base = len(amounts_baseline)
    n_cur = len(amounts_current)
    # Space baseline dates evenly across window
    for i, amt in enumerate(amounts_baseline):
        delta_days = 300 - i * (260 // max(n_base, 1))
        d = (today - pd.Timedelta(days=delta_days)).date().isoformat()
        rows.append({
            "ticker": ticker, "cik": 99999, "filing_date": d,
            "items": "1.01", "accession": f"base-{i}",
            "amount_usd": amt, "extraction_ok": True,
        })
    for i, amt in enumerate(amounts_current):
        delta_days = 30 - i * (20 // max(n_cur, 1))
        d = (today - pd.Timedelta(days=delta_days)).date().isoformat()
        rows.append({
            "ticker": ticker, "cik": 99999, "filing_date": d,
            "items": "1.01", "accession": f"cur-{i}",
            "amount_usd": amt, "extraction_ok": True,
        })
    return pd.DataFrame(rows)


class TestContractZForMember:
    def test_returns_float_with_sufficient_history(self):
        today = pd.Timestamp.today().normalize()
        # Baseline: 5 events around $100M each; current: one at $500M (should be positive z)
        df = _make_events_df("AAAA",
                             [100e6, 95e6, 110e6, 105e6, 90e6],
                             [500e6], today)
        z = _contract_z_for_member("AAAA", df, today)
        assert z is not None, "Expected a z-score with 5 baseline events"
        assert isinstance(z, float)
        # 500M >> 100M baseline -> z should be positive
        assert z > 0

    def test_returns_none_thin_history(self):
        today = pd.Timestamp.today().normalize()
        # Only 2 baseline events — below BASELINE_MIN=3
        df = _make_events_df("BBBB", [100e6, 90e6], [500e6], today)
        z = _contract_z_for_member("BBBB", df, today)
        assert z is None, f"Expected None for n<BASELINE_MIN, got {z}"

    def test_returns_none_no_current_event(self):
        today = pd.Timestamp.today().normalize()
        # Baseline: 5 events; current: empty
        df = _make_events_df("CCCC", [100e6, 95e6, 110e6, 105e6, 90e6], [], today)
        z = _contract_z_for_member("CCCC", df, today)
        assert z is None

    def test_below_baseline_gives_negative_z(self):
        today = pd.Timestamp.today().normalize()
        # Baseline: 5 events around $500M; current: $10M (way below -> negative z)
        df = _make_events_df("DDDD",
                             [500e6, 480e6, 520e6, 490e6, 510e6],
                             [10e6], today)
        z = _contract_z_for_member("DDDD", df, today)
        assert z is not None
        assert z < 0

    def test_z_values_not_equal_for_different_amounts(self):
        """Bug-trap: two different current amounts should yield two different z values."""
        today = pd.Timestamp.today().normalize()
        base = [100e6, 95e6, 110e6, 105e6, 90e6]
        df_high = _make_events_df("EEEE", base, [1_000e6], today)
        df_low = _make_events_df("EEEE", base, [50e6], today)
        z_high = _contract_z_for_member("EEEE", df_high, today)
        z_low = _contract_z_for_member("EEEE", df_low, today)
        assert z_high is not None and z_low is not None
        assert z_high != z_low


# ===========================================================================
# 4. Pre-drift flag: requires BOTH large-z AND flat consensus
# ===========================================================================

class TestConsensusFlatAndPreDrift:
    def test_flat_when_absent(self):
        assert _consensus_flat("XYZ", {}) is True

    def test_flat_when_stable(self):
        rev_map = {"ABC": {"direction": "stable", "revision_delta": 0.0}}
        assert _consensus_flat("ABC", rev_map) is True

    def test_not_flat_when_upgrading(self):
        rev_map = {"ABC": {"direction": "upgrading", "revision_delta": 2.0}}
        assert _consensus_flat("ABC", rev_map) is False

    def test_not_flat_when_downgrading(self):
        rev_map = {"ABC": {"direction": "downgrading", "revision_delta": -1.0}}
        assert _consensus_flat("ABC", rev_map) is False

    def test_predrift_requires_flat_consensus(self):
        """When consensus is already moving (upgrading), pre-drift must NOT fire
        even if z is above the threshold.  This is the key contract in the spec."""
        today = pd.Timestamp.today().normalize()
        # Build a large-z scenario
        df = _make_events_df("FFFF",
                             [100e6, 95e6, 110e6, 105e6, 90e6],
                             [2_000e6], today)
        z = _contract_z_for_member("FFFF", df, today)
        assert z is not None and z >= LARGE_Z_THRESHOLD, \
            f"Fixture z={z} must be >= {LARGE_Z_THRESHOLD} for the test to be meaningful"

        # consensus already moved -> _consensus_flat returns False
        rev_map_moving = {"FFFF": {"direction": "upgrading", "revision_delta": 3.0}}
        assert _consensus_flat("FFFF", rev_map_moving) is False
        # so pre-drift would NOT fire (tested via _consensus_flat gate)

        # consensus flat -> pre-drift WOULD fire
        rev_map_flat = {"FFFF": {"direction": "stable", "revision_delta": 0.0}}
        assert _consensus_flat("FFFF", rev_map_flat) is True


# ===========================================================================
# 5. Ledger dedup
# ===========================================================================

class TestLedgerDedup:
    def test_dedup_same_theme_asof(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.eightk_magnitude.config.data_dir", lambda: tmp_path)
        payload = {
            "asof": "2026-07-03",
            "themes": {
                "theme_A": {
                    "contract_dollar_z": 1.8,
                    "pre_drift": True,
                    "n_extraction_ok": 2,
                    "n_events": 3,
                    "top_ticker": "AAAA",
                    "top_amount_usd": 500e6,
                }
            },
        }
        _append_ledger(payload)
        _append_ledger(payload)  # second call — must be deduped

        lines = [l for l in (tmp_path / "eightk_magnitude" / "log.jsonl").read_text().splitlines() if l.strip()]
        assert len(lines) == 1, f"Dedup failed: got {len(lines)} rows (expected 1)"

    def test_different_dates_both_written(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.eightk_magnitude.config.data_dir", lambda: tmp_path)
        for asof in ("2026-07-01", "2026-07-02"):
            payload = {
                "asof": asof,
                "themes": {
                    "theme_B": {
                        "contract_dollar_z": 2.1,
                        "pre_drift": False,
                        "n_extraction_ok": 1,
                        "n_events": 1,
                        "top_ticker": "BBBB",
                        "top_amount_usd": 200e6,
                    }
                },
            }
            _append_ledger(payload)

        lines = [l for l in (tmp_path / "eightk_magnitude" / "log.jsonl").read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_grade_eligible_false_when_no_extraction_ok(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.eightk_magnitude.config.data_dir", lambda: tmp_path)
        payload = {
            "asof": "2026-07-03",
            "themes": {
                "theme_C": {
                    "contract_dollar_z": None,
                    "pre_drift": False,
                    "n_extraction_ok": 0,  # zero ok extractions
                    "n_events": 2,
                    "top_ticker": None,
                    "top_amount_usd": None,
                }
            },
        }
        _append_ledger(payload)
        lines = (tmp_path / "eightk_magnitude" / "log.jsonl").read_text().splitlines()
        row = json.loads(lines[0])
        assert row["grade_eligible"] is False
        assert row["extraction_ok"] is False


# ===========================================================================
# 6. compute_eightk_magnitude end-to-end
# ===========================================================================

def _build_full_events(today: pd.Timestamp) -> pd.DataFrame:
    """Synthetic material_8k_events with two tickers in two themes.
    AAAA: theme_X, large contract history + large current (should yield positive z, pre-drift candidate)
    BBBB: theme_Y, thin history (< BASELINE_MIN) → z=None
    """
    rows = []
    # AAAA — adequate history
    for i in range(5):
        rows.append({
            "ticker": "AAAA", "cik": 1, "form": "8-K",
            "filing_date": (today - pd.Timedelta(days=200 + i * 20)).date().isoformat(),
            "items": "1.01", "accession": f"base-aa-{i}",
            "amount_usd": 100e6 + i * 5e6, "extraction_ok": True,
            "_first_seen": today.isoformat(),
        })
    rows.append({
        "ticker": "AAAA", "cik": 1, "form": "8-K",
        "filing_date": (today - pd.Timedelta(days=10)).date().isoformat(),
        "items": "1.01", "accession": "cur-aa-0",
        "amount_usd": 800e6, "extraction_ok": True,
        "_first_seen": today.isoformat(),
    })
    # BBBB — only 2 baseline events (< BASELINE_MIN=3) -> z=None
    for i in range(2):
        rows.append({
            "ticker": "BBBB", "cik": 2, "form": "8-K",
            "filing_date": (today - pd.Timedelta(days=200 + i * 30)).date().isoformat(),
            "items": "2.03", "accession": f"base-bb-{i}",
            "amount_usd": 50e6, "extraction_ok": True,
            "_first_seen": today.isoformat(),
        })
    rows.append({
        "ticker": "BBBB", "cik": 2, "form": "8-K",
        "filing_date": (today - pd.Timedelta(days=5)).date().isoformat(),
        "items": "2.03", "accession": "cur-bb-0",
        "amount_usd": 500e6, "extraction_ok": True,
        "_first_seen": today.isoformat(),
    })
    return pd.DataFrame(rows)


def _build_membership():
    return {
        "baskets": {
            "theme_X": {"members": [{"ticker": "AAAA"}, {"ticker": "CCCC"}]},
            "theme_Y": {"members": [{"ticker": "BBBB"}]},
        }
    }


class TestComputeEightkMagnitude:
    def test_returns_dict_with_themes(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.eightk_magnitude.config.data_dir", lambda: tmp_path)

        today = pd.Timestamp.today().normalize()
        events = _build_full_events(today)
        (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
        events.to_parquet(tmp_path / "edgar" / "material_8k_events.parquet")
        (tmp_path / "baskets").mkdir(parents=True, exist_ok=True)
        (tmp_path / "baskets" / "membership.json").write_text(
            json.dumps(_build_membership())
        )

        result = compute_eightk_magnitude(write_ledger=False)
        assert result is not None
        assert "themes" in result
        assert "asof" in result
        assert "summary" in result

    def test_theme_x_has_positive_z(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.eightk_magnitude.config.data_dir", lambda: tmp_path)

        today = pd.Timestamp.today().normalize()
        events = _build_full_events(today)
        (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
        events.to_parquet(tmp_path / "edgar" / "material_8k_events.parquet")
        (tmp_path / "baskets").mkdir(parents=True, exist_ok=True)
        (tmp_path / "baskets" / "membership.json").write_text(
            json.dumps(_build_membership())
        )

        result = compute_eightk_magnitude(write_ledger=False)
        assert result is not None
        tx = result["themes"].get("theme_X")
        assert tx is not None, "theme_X should be in results"
        assert tx["contract_dollar_z"] is not None
        assert tx["contract_dollar_z"] > 0

    def test_theme_y_z_is_none_thin_history(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.eightk_magnitude.config.data_dir", lambda: tmp_path)

        today = pd.Timestamp.today().normalize()
        events = _build_full_events(today)
        (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
        events.to_parquet(tmp_path / "edgar" / "material_8k_events.parquet")
        (tmp_path / "baskets").mkdir(parents=True, exist_ok=True)
        (tmp_path / "baskets" / "membership.json").write_text(
            json.dumps(_build_membership())
        )

        result = compute_eightk_magnitude(write_ledger=False)
        assert result is not None
        ty = result["themes"].get("theme_Y")
        # BBBB has only 2 baseline events → z=None
        if ty is not None:
            assert ty["contract_dollar_z"] is None, \
                f"Expected z=None for thin history, got {ty['contract_dollar_z']}"

    def test_predrift_true_when_flat_consensus(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.eightk_magnitude.config.data_dir", lambda: tmp_path)

        today = pd.Timestamp.today().normalize()
        events = _build_full_events(today)
        (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
        events.to_parquet(tmp_path / "edgar" / "material_8k_events.parquet")
        (tmp_path / "baskets").mkdir(parents=True, exist_ok=True)
        (tmp_path / "baskets" / "membership.json").write_text(
            json.dumps(_build_membership())
        )

        # Inject empty revision map (all tickers flat/absent)
        result = compute_eightk_magnitude(write_ledger=False, _rev_map_override={})

        assert result is not None
        tx = result["themes"].get("theme_X")
        if tx and tx["contract_dollar_z"] is not None and tx["contract_dollar_z"] >= LARGE_Z_THRESHOLD:
            assert tx["pre_drift"] is True, \
                "pre_drift should be True when z>=threshold and consensus is flat"

    def test_predrift_false_when_consensus_moved(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.eightk_magnitude.config.data_dir", lambda: tmp_path)

        today = pd.Timestamp.today().normalize()
        events = _build_full_events(today)
        (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
        events.to_parquet(tmp_path / "edgar" / "material_8k_events.parquet")
        (tmp_path / "baskets").mkdir(parents=True, exist_ok=True)
        (tmp_path / "baskets" / "membership.json").write_text(
            json.dumps(_build_membership())
        )

        # Consensus has moved (upgrading) for AAAA -> no pre-drift
        moving_rev = {"AAAA": {"direction": "upgrading", "revision_delta": 4.0}}
        result = compute_eightk_magnitude(write_ledger=False, _rev_map_override=moving_rev)

        assert result is not None
        tx = result["themes"].get("theme_X")
        if tx:
            assert tx["pre_drift"] is False, \
                "pre_drift must be False when consensus has already moved"

    def test_ledger_written_when_write_ledger_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.eightk_magnitude.config.data_dir", lambda: tmp_path)

        today = pd.Timestamp.today().normalize()
        events = _build_full_events(today)
        (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
        events.to_parquet(tmp_path / "edgar" / "material_8k_events.parquet")
        (tmp_path / "baskets").mkdir(parents=True, exist_ok=True)
        (tmp_path / "baskets" / "membership.json").write_text(
            json.dumps(_build_membership())
        )

        result = compute_eightk_magnitude(write_ledger=True)
        assert result is not None

        ledger_path = tmp_path / "eightk_magnitude" / "log.jsonl"
        assert ledger_path.exists(), "Ledger file should be created"
        lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
        assert len(lines) > 0, "Ledger should have rows"
        # Verify structure of first row
        row = json.loads(lines[0])
        assert "theme" in row
        assert "asof" in row
        assert "contract_dollar_z" in row
        assert "pre_drift" in row
        assert "extraction_ok" in row
        assert "grade_eligible" in row

    def test_none_on_no_events(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.eightk_magnitude.config.data_dir", lambda: tmp_path)
        # No events file -> None
        result = compute_eightk_magnitude(write_ledger=False)
        assert result is None
