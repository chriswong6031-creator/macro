"""Tests for W4.5 — engine/regime_prior.py and scripts/build_regime_prior.py.

Coverage (per wave spec acceptance):

  (1) COMPOSER DEGRADES PER-COMPONENT
      - Missing data_dir sources → component status 'unavailable', merged status degrades
      - Fresh sources → merged status 'fresh'
      - Stale sources → merged status 'stale'

  (2) SNAPSHOT APPENDER KEEP-FIRST
      - Second append on the same date is a no-op (keep-first discipline)
      - Separate-date appends accumulate

  (3) BANNER TRIGGER LOGIC
      - check_staleness: stale=True when curated_as_of > 30d
      - check_staleness: stale=False when curated_as_of ≤ 30d
      - check_staleness: always returns checkable=False (honest limit, no machine-readable claims yet)

  (4) JS ARTIFACT PARSES
      - emit() produces a valid JS file containing window.REGIME_PRIOR = {...};
      - The JSON body is parseable; schema=1; required keys present

  (5) check_claims STUB
      - Returns [] when no narratives declare regime_claim
      - Returns a disagreement dict when a narrative's claimed quad != engine quad

All file-touching tests use tmp_path fixtures; no production data is modified.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


def _make_regime_latest(tmp: Path, quad: str = "Q1", asof: str | None = None) -> Path:
    asof = asof or _today()
    p = tmp / "regime" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": 1, "asof": asof, "date": asof,
        "quad": quad, "quad_name": "Goldilocks",
        "liquidity_overlay": "expanding", "cycle_tag": "mid",
        "transition_state": "STABLE", "transition_state_raw": "STABLE",
    }), encoding="utf-8")
    return p


def _make_market_state_latest(tmp: Path, verdict: str = "MIXED", asof: str | None = None) -> Path:
    asof = asof or _today()
    p = tmp / "market_state" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema": 1, "asof": asof, "verdict": verdict, "score": 50,
        "label_en": "Mixed", "label_zh": "混合", "color": "yellow",
        "is_display_only": True,
    }), encoding="utf-8")
    return p


def _make_site_dir(tmp: Path) -> Path:
    s = tmp / "site"
    s.mkdir(parents=True, exist_ok=True)
    return s


# ---------------------------------------------------------------------------
# (1) COMPOSER DEGRADES PER-COMPONENT

def test_composer_returns_schema_1_keys():
    """regime_prior() always returns a dict with schema=1 and required keys."""
    from engine.regime_prior import regime_prior

    # Patch out all I/O so the test is data-independent
    with patch("engine.regime_prior._read_regime_latest", return_value={}), \
         patch("engine.regime_prior._read_market_state_latest", return_value={}), \
         patch("engine.regime_prior._read_vol_regime", return_value={}), \
         patch("engine.regime_prior._read_business_cycle", return_value={}):
        prior = regime_prior()

    assert prior["schema"] == 1
    assert "quad" in prior
    assert "market_state" in prior
    assert prior["market_state"]["not_a_model_input"] is True
    assert "sources" in prior
    for src_key in ("regime", "market_state", "vol_regime", "business_cycle"):
        assert src_key in prior["sources"]


def test_composer_all_missing_degrades_to_unavailable():
    """All sources missing → merged status 'unavailable'."""
    from engine.regime_prior import regime_prior

    with patch("engine.regime_prior._read_regime_latest", return_value={}), \
         patch("engine.regime_prior._read_market_state_latest", return_value={}), \
         patch("engine.regime_prior._read_vol_regime", return_value={}), \
         patch("engine.regime_prior._read_business_cycle", return_value={}):
        prior = regime_prior()

    assert prior["status"] == "unavailable"


def test_composer_fresh_sources_yield_fresh_status(tmp_path):
    """All sources with today's asof → status 'fresh'."""
    from engine.regime_prior import regime_prior

    today = _today()
    _make_regime_latest(tmp_path, asof=today)
    _make_market_state_latest(tmp_path, asof=today)

    with patch("engine.regime_prior._read_vol_regime", return_value={"asof": today, "regime": "normalizing"}), \
         patch("engine.regime_prior._read_business_cycle", return_value={"asof": today, "phase": {"label": "expansion"}, "recession_signal": {}}):
        prior = regime_prior(data_dir=tmp_path)

    assert prior["status"] == "fresh"
    assert prior["quad"] == "Q1"
    assert prior["quad_name_en"] == "Goldilocks"
    assert prior["liquidity"] == "expanding"


def test_composer_stale_source_degrades_status(tmp_path):
    """One stale source (>5 days) → merged status 'stale'."""
    from engine.regime_prior import regime_prior

    today = _today()
    stale = _days_ago(10)
    _make_regime_latest(tmp_path, asof=stale)   # stale
    _make_market_state_latest(tmp_path, asof=today)

    with patch("engine.regime_prior._read_vol_regime", return_value={"asof": today, "regime": "normalizing"}), \
         patch("engine.regime_prior._read_business_cycle", return_value={"asof": today, "phase": {}, "recession_signal": {}}):
        prior = regime_prior(data_dir=tmp_path)

    assert prior["status"] == "stale"
    assert prior["sources"]["regime"]["status"] == "stale"


def test_composer_partial_when_one_source_missing(tmp_path):
    """One source absent, rest fresh → merged status 'partial'."""
    from engine.regime_prior import regime_prior

    today = _today()
    _make_regime_latest(tmp_path, asof=today)
    # market_state absent

    with patch("engine.regime_prior._read_vol_regime", return_value={"asof": today, "regime": "calm"}), \
         patch("engine.regime_prior._read_business_cycle", return_value={"asof": today, "phase": {}, "recession_signal": {}}):
        prior = regime_prior(data_dir=tmp_path)

    assert prior["status"] == "partial"


def test_composer_never_raises_on_empty_returns(tmp_path):
    """When all readers return {} (their own try/except swallowed errors),
    regime_prior() still returns a valid dict without raising."""
    from engine.regime_prior import regime_prior

    # Readers have try/except in their body and return {} on any failure;
    # test that {} inputs compose without raising.
    with patch("engine.regime_prior._read_regime_latest", return_value={}), \
         patch("engine.regime_prior._read_market_state_latest", return_value={}), \
         patch("engine.regime_prior._read_vol_regime", return_value={}), \
         patch("engine.regime_prior._read_business_cycle", return_value={}):
        prior = regime_prior(data_dir=tmp_path)

    assert isinstance(prior, dict)
    assert prior.get("schema") == 1
    assert prior.get("status") == "unavailable"


# ---------------------------------------------------------------------------
# (2) SNAPSHOT APPENDER KEEP-FIRST

def test_pit_append_keep_first(tmp_path):
    """Second append on same date is a no-op (keep-first discipline)."""
    import pandas as pd
    from scripts.build_regime_prior import _append_pit

    data_dir = tmp_path / "data"
    (data_dir / "regime").mkdir(parents=True, exist_ok=True)
    today = _today()

    prior = {"status": "fresh", "quad": "Q1", "liquidity": "expanding",
             "market_state": {"verdict": "RISK_ON", "score": 70},
             "vol_regime": "calm", "bc_phase": "expansion"}

    # First append
    _append_pit(data_dir, prior)
    hist1 = pd.read_parquet(data_dir / "regime" / "market_state_history.parquet")
    assert len(hist1) == 1
    assert hist1.iloc[0]["date"] == today
    assert hist1.iloc[0]["ms_verdict"] == "RISK_ON"

    # Second append same day — should not add a row
    prior2 = dict(prior)
    prior2["market_state"] = {"verdict": "RISK_OFF", "score": 20}
    _append_pit(data_dir, prior2)
    hist2 = pd.read_parquet(data_dir / "regime" / "market_state_history.parquet")
    assert len(hist2) == 1
    # First value preserved (RISK_ON), not overwritten
    assert hist2.iloc[0]["ms_verdict"] == "RISK_ON"


def test_pit_append_separate_dates(tmp_path):
    """Separate dates accumulate as separate rows."""
    import pandas as pd
    from scripts.build_regime_prior import _append_pit

    data_dir = tmp_path / "data"
    (data_dir / "regime").mkdir(parents=True, exist_ok=True)

    prior_base = {"status": "fresh", "quad": "Q1", "liquidity": "expanding",
                  "market_state": {"verdict": "RISK_ON", "score": 70},
                  "vol_regime": "calm", "bc_phase": "expansion"}

    # Simulate two different dates by writing the parquet directly with a past date
    import pandas as pd
    old_row = {"date": _days_ago(3), "quad": "Q2", "liquidity": "contracting",
               "ms_verdict": "MIXED", "ms_score": 50, "vol_regime": "stress",
               "bc_phase": "slowdown", "status": "fresh", "built_at": "2026-06-30T00:00:00+00:00"}
    pd.DataFrame([old_row]).to_parquet(data_dir / "regime" / "market_state_history.parquet", index=False)

    # Now append today's row
    _append_pit(data_dir, prior_base)
    hist = pd.read_parquet(data_dir / "regime" / "market_state_history.parquet")
    assert len(hist) == 2
    dates = set(hist["date"].tolist())
    assert _days_ago(3) in dates
    assert _today() in dates


# ---------------------------------------------------------------------------
# (3) BANNER TRIGGER LOGIC

def test_staleness_banner_fires_when_stale():
    """check_staleness returns stale=True for asof > 30 days old."""
    from engine.regime_prior import check_staleness

    old = _days_ago(45)
    result = check_staleness(old)
    assert result["stale"] is True
    assert result["days"] == 45
    assert old in result["banner_en"]
    assert old in result["banner_zh"]
    assert "45d" in result["banner_en"]


def test_staleness_banner_silent_when_fresh():
    """check_staleness returns stale=False for asof ≤ 30 days old."""
    from engine.regime_prior import check_staleness

    recent = _days_ago(10)
    result = check_staleness(recent)
    assert result["stale"] is False
    assert result["banner_en"] == ""
    assert result["banner_zh"] == ""


def test_staleness_handles_none_asof():
    """check_staleness handles None gracefully."""
    from engine.regime_prior import check_staleness

    result = check_staleness(None)
    assert result["stale"] is False
    assert result["days"] is None


def test_staleness_checkable_is_false():
    """check_staleness always reports checkable=False (honest limit: no machine-readable claims)."""
    from engine.regime_prior import check_staleness

    for asof in [_days_ago(5), _days_ago(45), None]:
        result = check_staleness(asof)
        assert result["checkable"] is False
        assert "regime_claim" in result["contradiction_note"]


# ---------------------------------------------------------------------------
# (4) JS ARTIFACT PARSES

def test_js_artifact_parses(tmp_path):
    """emit() writes a valid JS file; JSON body is parseable; required keys present."""
    from scripts.build_regime_prior import emit

    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"
    _make_regime_latest(data_dir, asof=_today())
    _make_market_state_latest(data_dir, asof=_today())

    with patch("engine.regime_prior._read_vol_regime", return_value={"asof": _today(), "regime": "normalizing"}), \
         patch("engine.regime_prior._read_business_cycle", return_value={"asof": _today(), "phase": {"label": "recovery"}, "recession_signal": {}}):
        prior = emit(data_dir=data_dir, site_dir=site_dir)

    js_path = site_dir / "regimedata" / "regime_prior.js"
    assert js_path.exists(), "regime_prior.js was not written"

    content = js_path.read_text(encoding="utf-8")
    assert "window.REGIME_PRIOR" in content
    # Extract the JSON body
    m = re.search(r"window\.REGIME_PRIOR\s*=\s*(\{.*\});", content, re.DOTALL)
    assert m, "window.REGIME_PRIOR assignment not found in JS"
    parsed = json.loads(m.group(1))
    assert parsed["schema"] == 1
    assert "quad" in parsed
    assert "market_state" in parsed
    assert parsed["market_state"]["not_a_model_input"] is True
    assert "sources" in parsed
    assert "vol_regime" in parsed


def test_js_artifact_never_raises_on_missing_data(tmp_path):
    """emit() gracefully handles completely absent data sources."""
    from scripts.build_regime_prior import emit

    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"
    # No regime or market_state files present; no vol_regime/bc mocks

    with patch("engine.regime_prior._read_vol_regime", return_value={}), \
         patch("engine.regime_prior._read_business_cycle", return_value={}):
        prior = emit(data_dir=data_dir, site_dir=site_dir)

    assert prior["schema"] == 1
    assert prior["status"] == "unavailable"
    js_path = site_dir / "regimedata" / "regime_prior.js"
    assert js_path.exists()


def test_dry_run_does_not_write_files(tmp_path):
    """emit(dry_run=True) returns the prior dict without writing any files."""
    from scripts.build_regime_prior import emit

    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"

    with patch("engine.regime_prior._read_vol_regime", return_value={}), \
         patch("engine.regime_prior._read_business_cycle", return_value={}):
        prior = emit(data_dir=data_dir, site_dir=site_dir, dry_run=True)

    assert prior["schema"] == 1
    assert not (site_dir / "regimedata" / "regime_prior.js").exists()
    assert not (data_dir / "regime" / "market_state_history.parquet").exists()


# ---------------------------------------------------------------------------
# (5) check_claims STUB

def test_check_claims_returns_empty_for_no_regime_claim():
    """check_claims returns [] when narratives carry no regime_claim field."""
    from engine.regime_prior import check_claims

    narratives = [
        {"id": "oil", "regimeNote": "Headwind: strong dollar."},
        {"id": "gold", "regimeNote": "Tailwind: haven demand."},
        {"id": "null-opt-out", "regime_claim": None},  # explicit null opt-out
    ]
    prior = {"quad": "Q1", "sources": {"regime": {"asof": _today()}}}
    result = check_claims(narratives, prior=prior)
    assert result == []


def test_check_claims_detects_contradiction():
    """check_claims returns a disagreement when claimed quad != engine quad."""
    from engine.regime_prior import check_claims

    narratives = [
        {
            "id": "semis",
            "regime_claim": {"quad": "Q3", "as_of": _days_ago(10)},
        }
    ]
    prior = {"quad": "Q1", "sources": {"regime": {"asof": _today()}}}
    result = check_claims(narratives, prior=prior)
    assert len(result) == 1
    assert result[0]["claimed_quad"] == "Q3"
    assert result[0]["engine_quad"] == "Q1"
    assert "Q3" in result[0]["banner_en"]
    assert "Q1" in result[0]["banner_en"]
    assert "Q3" in result[0]["banner_zh"]


def test_check_claims_no_disagreement_when_quads_match():
    """check_claims returns [] when claimed and engine quad agree."""
    from engine.regime_prior import check_claims

    narratives = [{"id": "semis", "regime_claim": {"quad": "Q1", "as_of": _today()}}]
    prior = {"quad": "Q1", "sources": {"regime": {"asof": _today()}}}
    assert check_claims(narratives, prior=prior) == []


def test_check_claims_empty_narratives_list():
    """check_claims returns [] for empty or None narratives."""
    from engine.regime_prior import check_claims

    prior = {"quad": "Q1", "sources": {"regime": {"asof": _today()}}}
    assert check_claims([], prior=prior) == []
    assert check_claims(None, prior=prior) == []
