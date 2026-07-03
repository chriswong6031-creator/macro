"""Hermetic tests for the Federal Register collector (W0b).

All tests use synthetic fixtures; no network calls are made.

Test coverage:
1. Two-stage filter: term-only match without agency match -> dropped.
2. Two-stage filter: agency+term match -> kept.
3. significant=null is never counted in recent_sig_count.
4. theme_event frame shape test: loads through _load_theme_event + _theme_event_metric round-trip.
5. velocity window logic: recent vs prior bucketing is correct.
6. Parser/theme-mapper: monkeypatched HTTP fixture drives full fetch() path.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from collectors.federal_register import (
    FederalRegisterAdapter,
    _agency_slugs,
    _reg_stage,
    velocity,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_doc(
    doc_number: str = "DOC-001",
    doc_type: str = "RULE",
    action: str = "",
    significant: bool | None = None,
    pub_date: str = "2026-04-01",
    agencies: list[dict] | None = None,
    comments_close: str | None = None,
) -> dict:
    """Minimal synthetic Federal Register document dict."""
    return {
        "document_number": doc_number,
        "type": doc_type,
        "action": action,
        "significant": significant,
        "publication_date": pub_date,
        "agencies": agencies or [{"slug": "energy-department", "name": "Energy Department"}],
        "title": f"Test Rule {doc_number}",
        "abstract": "Test abstract",
        "comments_close_on": comments_close,
        "regulation_id_numbers": [],
        "docket_ids": [],
        "cfr_references": [],
    }


def _make_theme_map(theme_id: str = "nuclear_power",
                    terms: list[str] | None = None,
                    agencies: list[str] | None = None) -> dict:
    return {
        theme_id: {
            "terms": terms or ["nuclear reactor"],
            "agencies": agencies or ["nuclear-regulatory-commission", "energy-department"],
        }
    }


# ---------------------------------------------------------------------------
# 1. Two-stage filter: term match without agency match -> doc DROPPED
# ---------------------------------------------------------------------------

class TestTwoStageFilterTermOnly:
    """Stage-2 agency gate must DROP a doc that passes term but not agency."""

    def test_term_only_no_agency_match_dropped(self, tmp_path, monkeypatch):
        """Doc has agency 'commerce-department' but theme requires 'nuclear-regulatory-commission'.
        The doc must be silently dropped (no rows in output)."""
        theme_map = {
            "nuclear_power": {
                "terms": ["nuclear reactor"],
                "agencies": ["nuclear-regulatory-commission"],  # strict: only NRC
            }
        }
        doc = _make_doc(
            doc_number="RULE-2026-001",
            agencies=[{"slug": "commerce-department", "name": "Commerce"}],
        )

        # Monkeypatch theme_map loader and HTTP fetch
        monkeypatch.setattr(
            "collectors.federal_register._theme_map", lambda: theme_map
        )

        def mock_fetch_all(term, gte, lte, ua):
            return [doc]

        monkeypatch.setattr("collectors.federal_register._fetch_all_for_term", mock_fetch_all)

        adapter = FederalRegisterAdapter()
        # Patch config
        monkeypatch.setattr("collectors.federal_register.config.load",
                            lambda: {"sponsors": {"user_agent": "test/1.0"}})
        monkeypatch.setattr("collectors.federal_register.config.data_dir",
                            lambda: tmp_path)

        result = adapter.fetch(full_history=False)

        # Check: docs.parquet has 0 rows (doc was filtered out)
        docs_path = tmp_path / "federal_register" / "documents.parquet"
        if docs_path.exists():
            df = pd.read_parquet(docs_path)
            assert len(df) == 0, f"Expected 0 docs, got {len(df)}: {df.to_dict()}"
        # velocity parquet should not exist or be empty
        vel_path = tmp_path / "federal_register" / "reg_velocity.parquet"
        if vel_path.exists():
            vel = pd.read_parquet(vel_path)
            assert vel.empty or "nuclear_power" not in vel.index


# ---------------------------------------------------------------------------
# 2. Two-stage filter: agency+term match -> doc KEPT
# ---------------------------------------------------------------------------

class TestTwoStageFilterAgencyAndTermKept:
    """A doc matching both term AND agency must be kept."""

    def test_agency_and_term_match_kept(self, tmp_path, monkeypatch):
        theme_map = {
            "nuclear_power": {
                "terms": ["nuclear reactor"],
                "agencies": ["nuclear-regulatory-commission", "energy-department"],
            }
        }
        doc = _make_doc(
            doc_number="RULE-NRC-001",
            agencies=[{"slug": "nuclear-regulatory-commission", "name": "NRC"}],
            pub_date="2026-04-01",
        )

        monkeypatch.setattr("collectors.federal_register._theme_map", lambda: theme_map)
        monkeypatch.setattr("collectors.federal_register._fetch_all_for_term",
                            lambda term, gte, lte, ua: [doc])
        monkeypatch.setattr("collectors.federal_register.config.load",
                            lambda: {"sponsors": {"user_agent": "test/1.0"}})
        monkeypatch.setattr("collectors.federal_register.config.data_dir",
                            lambda: tmp_path)

        adapter = FederalRegisterAdapter()
        adapter.fetch(full_history=False)

        docs_path = tmp_path / "federal_register" / "documents.parquet"
        assert docs_path.exists(), "documents.parquet must exist"
        df = pd.read_parquet(docs_path)
        assert len(df) == 1, f"Expected 1 doc, got {len(df)}"
        assert df.iloc[0]["document_number"] == "RULE-NRC-001"
        assert df.iloc[0]["basket_id"] == "nuclear_power"


# ---------------------------------------------------------------------------
# 3. significant=null never counted in recent_sig_count
# ---------------------------------------------------------------------------

class TestSignificantNull:
    """null significant value must NOT be counted in recent_sig_count."""

    def test_null_significant_not_counted(self):
        today = pd.Timestamp("2026-07-03")
        rows = [
            {"basket_id": "nuclear_power", "publication_date": "2026-05-01",
             "significant": True,  "weight": 1.5},
            {"basket_id": "nuclear_power", "publication_date": "2026-05-02",
             "significant": None,  "weight": 0.8},   # null -> NOT significant
            {"basket_id": "nuclear_power", "publication_date": "2026-05-03",
             "significant": False, "weight": 0.8},   # false -> NOT significant
        ]
        docs = pd.DataFrame(rows)
        vel = velocity(docs, today=today, recent_d=90, prior_d=90)

        assert "nuclear_power" in vel.index
        row = vel.loc["nuclear_power"]
        assert row["recent_count"] == 3, f"Expected 3, got {row['recent_count']}"
        assert row["recent_sig_count"] == 1, (
            f"Only 1 doc has significant=True; got {row['recent_sig_count']}"
        )

    def test_all_null_significant_zero_sig_count(self):
        today = pd.Timestamp("2026-07-03")
        rows = [
            {"basket_id": "ai_semiconductors", "publication_date": "2026-05-01",
             "significant": None, "weight": 0.8},
            {"basket_id": "ai_semiconductors", "publication_date": "2026-05-15",
             "significant": None, "weight": 0.8},
        ]
        docs = pd.DataFrame(rows)
        vel = velocity(docs, today=today)
        assert "ai_semiconductors" in vel.index
        assert vel.loc["ai_semiconductors"]["recent_sig_count"] == 0


# ---------------------------------------------------------------------------
# 4. theme_event frame shape test: _load_theme_event + _theme_event_metric round-trip
# ---------------------------------------------------------------------------

class TestThemeEventFrameShape:
    """reg_velocity.parquet must satisfy _load_theme_event and _theme_event_metric."""

    def test_load_theme_event_round_trip(self, tmp_path):
        """Build a minimal reg_velocity frame and verify the theme_activity loaders work."""
        from engine.theme_activity import SOURCES, _load_theme_event, _theme_event_metric

        # Find the fedreg_velocity source
        src = next((s for s in SOURCES if s["name"] == "fedreg_velocity"), None)
        assert src is not None, "fedreg_velocity must be in SOURCES"
        assert src["kind"] == "theme_event"
        assert src["group"] == "federal_register"
        assert src["series"] == "reg_velocity"

        # Build a synthetic velocity frame and inject via sources_data
        vel_df = pd.DataFrame([
            {"basket_id": "nuclear_power", "recent_count": 5, "prior_count": 2, "recent_sig_count": 2},
            {"basket_id": "ai_semiconductors", "recent_count": 0, "prior_count": 0, "recent_sig_count": 0},
        ]).set_index("basket_id")

        sources_data = {"fedreg_velocity": vel_df}

        # Test _load_theme_event injection path
        loaded = _load_theme_event(src, sources_data)
        assert loaded is not None, "_load_theme_event must return a frame"
        assert "nuclear_power" in loaded.index
        assert "recent_count" in loaded.columns
        assert "prior_count" in loaded.columns
        assert "recent_sig_count" in loaded.columns

        # Test _theme_event_metric for a basket with activity
        result = _theme_event_metric(src, "nuclear_power", frame=loaded)
        assert result is not None, "_theme_event_metric must return a dict for nuclear_power"
        assert "accel" in result
        assert "recent_count" in result
        assert result["recent_count"] == 5
        assert result["prior_count"] == 2
        assert result["accel"] > 1.0, "recent > prior so accel should be > 1"

        # Test _theme_event_metric for a basket with zero activity -> None (silent)
        result_zero = _theme_event_metric(src, "ai_semiconductors", frame=loaded)
        assert result_zero is None, "Both-zero basket must return None (silent)"

    def test_load_theme_event_absent_returns_none(self):
        """When sources_data is not injected and parquet is absent, loader returns None."""
        from engine.theme_activity import _load_theme_event, SOURCES

        src = next(s for s in SOURCES if s["name"] == "fedreg_velocity")
        # sources_data=None -> disk read path; parquet absent -> None
        with patch("engine.theme_activity.config.data_dir") as mock_dir:
            from pathlib import Path
            mock_dir.return_value = Path("/nonexistent_path_for_test_xyz")
            result = _load_theme_event(src, None)
        assert result is None


# ---------------------------------------------------------------------------
# 5. velocity window logic
# ---------------------------------------------------------------------------

class TestVelocityWindowLogic:
    """Verify recent vs prior window bucketing is correct."""

    def test_recent_vs_prior_bucketing(self):
        today = pd.Timestamp("2026-07-03")
        # recent window: 2026-04-04 to 2026-07-03 (90d)
        # prior window: 2026-01-04 to 2026-04-04 (90d prior)
        rows = [
            # In recent window
            {"basket_id": "solar", "publication_date": "2026-06-01", "significant": True,  "weight": 1.5},
            {"basket_id": "solar", "publication_date": "2026-05-01", "significant": False, "weight": 1.5},
            # In prior window
            {"basket_id": "solar", "publication_date": "2026-02-01", "significant": True,  "weight": 1.5},
            # Outside both windows
            {"basket_id": "solar", "publication_date": "2025-01-01", "significant": True,  "weight": 1.5},
        ]
        docs = pd.DataFrame(rows)
        vel = velocity(docs, today=today, recent_d=90, prior_d=90)

        assert "solar" in vel.index
        row = vel.loc["solar"]
        assert row["recent_count"] == 2, f"Expected 2 recent, got {row['recent_count']}"
        assert row["prior_count"] == 1, f"Expected 1 prior, got {row['prior_count']}"
        assert row["recent_sig_count"] == 1, f"Expected 1 sig recent, got {row['recent_sig_count']}"

    def test_empty_docs_returns_empty(self):
        vel = velocity(pd.DataFrame(), today=pd.Timestamp("2026-07-03"))
        assert vel.empty

    def test_none_docs_returns_empty(self):
        vel = velocity(None, today=pd.Timestamp("2026-07-03"))
        assert vel.empty

    def test_no_activity_in_windows_excluded(self):
        """Docs outside both windows are excluded from the output frame."""
        rows = [
            {"basket_id": "cybersecurity", "publication_date": "2020-01-01",
             "significant": True, "weight": 1.0},
        ]
        docs = pd.DataFrame(rows)
        vel = velocity(docs, today=pd.Timestamp("2026-07-03"), recent_d=90, prior_d=90)
        # cybersecurity should NOT appear (both counts are 0)
        assert "cybersecurity" not in vel.index


# ---------------------------------------------------------------------------
# 6. reg_stage parser
# ---------------------------------------------------------------------------

class TestRegStage:
    def test_rule_interim_final(self):
        stage, weight = _reg_stage("RULE", "interim final rule effective immediately")
        assert stage == "interim_final_rule"
        assert weight == 1.8

    def test_rule_final(self):
        stage, weight = _reg_stage("RULE", "Final rule.")
        assert stage == "final_rule"
        assert weight == 1.5

    def test_prorule(self):
        stage, weight = _reg_stage("PRORULE", "Proposed rule.")
        assert stage == "proposed_rule"
        assert weight == 0.8

    def test_presdocu(self):
        stage, weight = _reg_stage("PRESDOCU", "Executive Order 14000")
        assert stage == "executive_order"
        assert weight == 2.0

    def test_notice_rfi(self):
        stage, weight = _reg_stage("NOTICE", "Request for information on AI safety")
        assert stage == "rfi"
        assert weight == 0.4

    def test_notice_funding(self):
        stage, weight = _reg_stage("NOTICE", "Notice of funding opportunity")
        assert stage == "funding_notice"
        assert weight == 0.6


# ---------------------------------------------------------------------------
# 7. _agency_slugs helper
# ---------------------------------------------------------------------------

class TestAgencySlugs:
    def test_extracts_slugs(self):
        agencies = [
            {"slug": "energy-department", "name": "Dept. of Energy"},
            {"slug": "nuclear-regulatory-commission", "name": "NRC"},
        ]
        slugs = _agency_slugs(agencies)
        assert slugs == {"energy-department", "nuclear-regulatory-commission"}

    def test_empty_list(self):
        assert _agency_slugs([]) == set()

    def test_missing_slug_key(self):
        agencies = [{"name": "Some Agency"}]  # no slug key
        assert _agency_slugs(agencies) == set()


# ---------------------------------------------------------------------------
# 8. fedreg_velocity is correctly registered in SOURCES
# ---------------------------------------------------------------------------

class TestSourcesRegistration:
    def test_fedreg_in_sources(self):
        from engine.theme_activity import SOURCES

        names = [s["name"] for s in SOURCES]
        assert "fedreg_velocity" in names, f"fedreg_velocity not in SOURCES: {names}"

        src = next(s for s in SOURCES if s["name"] == "fedreg_velocity")
        assert src["kind"] == "theme_event"
        assert src["group"] == "federal_register"
        assert src["series"] == "reg_velocity"
        assert "label_en" in src
        assert "label_zh" in src
        assert src["weight"] > 0

    def test_fedreg_is_last_theme_event(self):
        """fedreg_velocity should be the last entry in SOURCES (END-append rule)."""
        from engine.theme_activity import SOURCES

        assert SOURCES[-1]["name"] == "fedreg_velocity", (
            f"fedreg_velocity must be the last SOURCES entry; got {SOURCES[-1]['name']!r}"
        )
