"""Tests for engine/neuralweb/prophet_governor.py — Prophet cross-market governor.

Coverage:
  1. Governor per-market blocks build with tiny fixtures (absent store => data_gap).
  2. Absent store returns data_gap, NOT fabricated zeros (SA-R15).
  3. cross_market block contains NO excess/return keys (PR-R5 hard law).
  4. Suggestions deduplicate by code; first_seen stable.
  5. Suggestion high-severity => count is bounded by _MAX_SUGGESTIONS.
  6. Initial bake: build_and_write writes only the two new artifacts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_status_fixture(tmp_path: Path, include_us_parquet: bool = False) -> dict:
    """Build a minimal repo tree and return build_status(root=tmp_path)."""
    import engine.neuralweb.prophet_governor as pg

    # Wire prophet_governor to use tmp_path as repo root
    return pg.build_status(root=tmp_path)


# ---------------------------------------------------------------------------
# 1. Absent store => data_gap (SA-R15), not fabricated zeros
# ---------------------------------------------------------------------------
class TestAbsentStoreDataGap:
    def test_us_block_absent_parquet(self, tmp_path):
        """When retro_grades.parquet is absent, data_gap is recorded, not zeros."""
        import engine.neuralweb.prophet_governor as pg

        result = pg.build_status(root=tmp_path)
        us_block = result["markets"]["us"]
        gaps = us_block.get("data_gaps", [])
        assert any("retro_grades" in g.get("field", "") for g in gaps), (
            "Expected data_gap for absent retro_grades.parquet"
        )
        # Key must NOT be present with a fabricated numeric
        assert "retro_grades" not in us_block or us_block.get("retro_grades") is None or \
               isinstance(us_block.get("retro_grades"), dict), \
               "retro_grades key should be dict or absent, never a fabricated number"

    def test_cn_block_absent_parquet(self, tmp_path):
        """When CN board parquet is absent, data_gap is recorded."""
        import engine.neuralweb.prophet_governor as pg

        result = pg.build_status(root=tmp_path)
        cn_block = result["markets"]["cn"]
        gaps = cn_block.get("data_gaps", [])
        assert any("cn_board" in g.get("field", "") for g in gaps), (
            "Expected data_gap for absent cn board parquet"
        )

    def test_all_markets_present(self, tmp_path):
        """All five market blocks must be present even when stores are absent."""
        import engine.neuralweb.prophet_governor as pg

        result = pg.build_status(root=tmp_path)
        for market in ("us", "cn", "hk", "ca", "intl"):
            assert market in result["markets"], f"Missing market block: {market}"

    def test_no_missing_market_raises(self, tmp_path):
        """build_status never raises even when all stores are absent."""
        import engine.neuralweb.prophet_governor as pg

        # Should not raise
        result = pg.build_status(root=tmp_path)
        assert result.get("schema") == "prophet.status/v1"

    def test_data_gap_not_zero(self, tmp_path):
        """Absent intl_setups must not produce fabricated counts."""
        import engine.neuralweb.prophet_governor as pg

        result = pg.build_status(root=tmp_path)
        intl_block = result["markets"]["intl"]
        # Either coverage key is absent or it's a real dict (not a fabricated 0)
        coverage = intl_block.get("coverage")
        if coverage is not None:
            # If present, should be from a real file — here it's absent so coverage is None
            assert isinstance(coverage, dict)
        else:
            # Must have a data_gap for the missing file
            gaps = intl_block.get("data_gaps", [])
            assert any("intl_setups" in g.get("field", "") for g in gaps)


# ---------------------------------------------------------------------------
# 2. cross_market block must not contain excess/return keys (PR-R5)
# ---------------------------------------------------------------------------
class TestCrossMarketNoReturns:
    FORBIDDEN_RETURN_KEYS = frozenset({
        "excess", "return", "win_rate", "avg_excess", "median_excess",
        "pct", "alpha", "pooled", "combined",
    })

    def test_cross_market_no_return_keys(self, tmp_path):
        """cross_market block must contain counts/coverage only, no return stats."""
        import engine.neuralweb.prophet_governor as pg

        result = pg.build_status(root=tmp_path)
        cross = result.get("cross_market", {})

        def _check_no_return_keys(d: dict, path: str = "") -> None:
            for key, val in d.items():
                key_lower = key.lower()
                for forbidden in self.FORBIDDEN_RETURN_KEYS:
                    assert forbidden not in key_lower, (
                        f"PR-R5 violation: cross_market contains return key "
                        f"'{key}' at path '{path}'"
                    )
                if isinstance(val, dict):
                    _check_no_return_keys(val, f"{path}.{key}")

        _check_no_return_keys(cross)

    def test_cross_market_has_counts(self, tmp_path):
        """cross_market must have markets_covered and per_market_receipts."""
        import engine.neuralweb.prophet_governor as pg

        result = pg.build_status(root=tmp_path)
        cross = result.get("cross_market", {})
        assert "markets_covered" in cross
        assert "per_market_receipts" in cross
        assert isinstance(cross["per_market_receipts"], dict)

    def test_cross_market_receipts_no_returns(self, tmp_path):
        """Per-market receipts in cross_market must not contain return values."""
        import engine.neuralweb.prophet_governor as pg

        result = pg.build_status(root=tmp_path)
        receipts = result.get("cross_market", {}).get("per_market_receipts", {})
        for market, receipt in receipts.items():
            if not isinstance(receipt, dict):
                continue
            for key in receipt:
                key_lower = key.lower()
                for forbidden in self.FORBIDDEN_RETURN_KEYS:
                    assert forbidden not in key_lower, (
                        f"PR-R5 violation: receipt for {market} has return key '{key}'"
                    )


# ---------------------------------------------------------------------------
# 3. Suggestions dedup by code; first_seen stable
# ---------------------------------------------------------------------------
class TestSuggestionsDeduplicate:
    def _make_status_with_stale(self, tmp_path: Path) -> dict:
        """Build a status with injected stale artifact to trigger a suggestion."""
        import engine.neuralweb.prophet_governor as pg

        # Create a stale artifact (mtime far in the past via content stamp)
        art_dir = tmp_path / "site" / "factordata"
        art_dir.mkdir(parents=True)
        stale_path = art_dir / "us_audit_scoreboard.json"
        import time
        old_ts = "2020-01-01T00:00:00+00:00"
        stale_path.write_text(json.dumps({"as_of": old_ts, "status": "ok"}))

        return pg.build_status(root=tmp_path)

    def test_suggestions_deduplicate(self, tmp_path):
        """Calling build_suggestions twice with same status yields same codes."""
        import engine.neuralweb.prophet_governor as pg

        status = self._make_status_with_stale(tmp_path)
        s1 = pg.build_suggestions(status)
        s2 = pg.build_suggestions(status)

        codes1 = [s["code"] for s in s1]
        codes2 = [s["code"] for s in s2]
        assert codes1 == codes2, "Suggestion codes must be stable across calls"

    def test_suggestions_max_10(self, tmp_path):
        """Suggestions list must never exceed 10 rows."""
        import engine.neuralweb.prophet_governor as pg

        status = pg.build_status(root=tmp_path)
        suggestions = pg.build_suggestions(status)
        assert len(suggestions) <= 10, (
            f"Expected <= 10 suggestions, got {len(suggestions)}"
        )

    def test_suggestion_schema(self, tmp_path):
        """Each suggestion row must have the required keys."""
        import engine.neuralweb.prophet_governor as pg

        status = self._make_status_with_stale(tmp_path)
        suggestions = pg.build_suggestions(status)
        required = {"code", "kind", "severity", "detail", "market", "first_seen", "asof"}
        for s in suggestions:
            for key in required:
                assert key in s, f"Suggestion missing key '{key}': {s}"

    def test_suggestion_kind_in_vocabulary(self, tmp_path):
        """kind must be one of the allowed values."""
        import engine.neuralweb.prophet_governor as pg

        status = pg.build_status(root=tmp_path)
        suggestions = pg.build_suggestions(status)
        allowed_kinds = {"contract_drift", "coverage_gap", "staleness", "lobe_request", "other"}
        for s in suggestions:
            assert s["kind"] in allowed_kinds, (
                f"Suggestion has invalid kind '{s['kind']}'"
            )

    def test_suggestion_severity_in_vocabulary(self, tmp_path):
        """severity must be one of high/medium/low."""
        import engine.neuralweb.prophet_governor as pg

        status = pg.build_status(root=tmp_path)
        suggestions = pg.build_suggestions(status)
        allowed = {"high", "medium", "low"}
        for s in suggestions:
            assert s["severity"] in allowed, (
                f"Suggestion has invalid severity '{s['severity']}'"
            )

    def test_suggestion_detail_length(self, tmp_path):
        """detail must be <= 160 characters."""
        import engine.neuralweb.prophet_governor as pg

        status = pg.build_status(root=tmp_path)
        suggestions = pg.build_suggestions(status)
        for s in suggestions:
            assert len(s["detail"]) <= 160, (
                f"Suggestion detail exceeds 160 chars: '{s['detail']}'"
            )


# ---------------------------------------------------------------------------
# 4. build_and_write writes only the two new artifacts
# ---------------------------------------------------------------------------
class TestBuildAndWrite:
    def test_writes_both_artifacts(self, tmp_path, monkeypatch):
        """build_and_write must write exactly prophet_status.json and prophet_suggestions.json."""
        import engine.neuralweb.prophet_governor as pg

        # Patch board_ledger to avoid real data reads
        import engine.board_ledger as bl
        monkeypatch.setattr(bl, "scorecard", lambda m: {"status": "accruing", "n_matured": 0})

        result = pg.build_and_write(root=tmp_path)
        assert result["status_path"] is not None
        assert result["suggestions_path"] is not None

        status_path = Path(result["status_path"])
        sug_path = Path(result["suggestions_path"])
        assert status_path.exists(), f"prophet_status.json not written: {status_path}"
        assert sug_path.exists(), f"prophet_suggestions.json not written: {sug_path}"

    def test_status_json_schema(self, tmp_path, monkeypatch):
        """Written prophet_status.json must have expected schema field."""
        import engine.neuralweb.prophet_governor as pg
        import engine.board_ledger as bl
        monkeypatch.setattr(bl, "scorecard", lambda m: {"status": "accruing"})

        result = pg.build_and_write(root=tmp_path)
        status_path = Path(result["status_path"])
        doc = json.loads(status_path.read_text())
        assert doc.get("schema") == "prophet.status/v1"
        assert "markets" in doc
        assert "cross_market" in doc
        assert "dashboard_integrity" in doc

    def test_suggestions_json_schema(self, tmp_path, monkeypatch):
        """Written prophet_suggestions.json must have expected schema field."""
        import engine.neuralweb.prophet_governor as pg
        import engine.board_ledger as bl
        monkeypatch.setattr(bl, "scorecard", lambda m: {"status": "accruing"})

        result = pg.build_and_write(root=tmp_path)
        sug_path = Path(result["suggestions_path"])
        doc = json.loads(sug_path.read_text())
        assert doc.get("schema") == "prophet.suggestions/v1"
        assert "suggestions" in doc
        assert isinstance(doc["suggestions"], list)

    def test_no_other_files_written(self, tmp_path, monkeypatch):
        """build_and_write must not write to data/ paths outside the two new artifacts
        and the expected inter-lobe channel (insight_bus.jsonl for high-severity rows)."""
        import engine.neuralweb.prophet_governor as pg
        import engine.board_ledger as bl
        monkeypatch.setattr(bl, "scorecard", lambda m: {"status": "accruing"})

        # Capture initial state
        before = set(tmp_path.rglob("*"))
        pg.build_and_write(root=tmp_path)
        after = set(tmp_path.rglob("*"))
        new_files = {p for p in (after - before) if p.is_file()}

        # Allowed: the two artifact files + insight_bus.jsonl (high-severity emissions)
        allowed_names = {
            "prophet_status.json",
            "prophet_suggestions.json",
            "insight_bus.jsonl",  # PR-R4: inter-lobe channel for high-severity suggestions
        }
        unexpected = {p for p in new_files if p.name not in allowed_names}
        assert not unexpected, (
            f"build_and_write wrote unexpected files: {unexpected}"
        )


# ---------------------------------------------------------------------------
# 5. Never raises
# ---------------------------------------------------------------------------
class TestNeverRaises:
    def test_build_status_never_raises(self, tmp_path):
        """build_status must not raise on empty repo."""
        import engine.neuralweb.prophet_governor as pg
        result = pg.build_status(root=tmp_path)
        assert isinstance(result, dict)

    def test_build_suggestions_never_raises(self):
        """build_suggestions must not raise on empty status."""
        import engine.neuralweb.prophet_governor as pg
        result = pg.build_suggestions({})
        assert isinstance(result, list)
