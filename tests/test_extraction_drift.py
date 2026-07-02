"""Tests for scripts/check_extraction_drift.py — drift gate math, anchor schema, off-state.

Tests:
  - Anchor schema validation (valid + malformed records)
  - Gate math: perfect predictions → gate_pass True; random predictions → varies
  - Dry-run mode: no LLM calls, returns gate_pass True on synthetic gold echoes
  - news_llm off-state: annotate() is a no-op when enabled=False (from config or env)
  - Degraded-render fixtures: degraded records carry expected keys
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_extraction_drift import (
    _validate_anchor,
    _score_predictions,
    dry_run,
    load_anchors,
    FIELD_AGREE_GATE,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_anchor(
    anchor_id="test_001",
    direction="bullish",
    magnitude=2,
    confidence="medium",
    reversibility="permanent",
    source_lane="edgar_8k",
):
    return {
        "anchor_id": anchor_id,
        "source_lane": source_lane,
        "source_id": "abc123",
        "body": "Company agreed to acquire Acme Corp for $5B premium cash deal.",
        "entity": "AcmeCorp",
        "date": "2026-06-01",
        "gold": {
            "direction": direction,
            "magnitude": magnitude,
            "confidence": confidence,
            "reversibility": reversibility,
            "quote_span": "agreed to acquire Acme Corp for $5B",
            "dropped_fields": [],
        },
        "gold_source": "model-bootstrap pending human review",
        "notes": "test anchor",
    }


# ---------------------------------------------------------------------------
# anchor schema validation
# ---------------------------------------------------------------------------

def test_validate_anchor_passes_valid():
    _validate_anchor(_make_anchor(), 1)  # must not raise


def test_validate_anchor_missing_required_field():
    rec = _make_anchor()
    del rec["source_id"]
    try:
        _validate_anchor(rec, 1)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_validate_anchor_missing_gold_field():
    rec = _make_anchor()
    del rec["gold"]["direction"]
    try:
        _validate_anchor(rec, 1)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_validate_anchor_invalid_direction():
    rec = _make_anchor()
    rec["gold"]["direction"] = "sideways"
    try:
        _validate_anchor(rec, 1)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_load_anchors_malformed_raises(tmp_path):
    f = tmp_path / "bad.jsonl"
    f.write_text('{"anchor_id": "ok", "source_lane": "x", "source_id": "y", '
                 '"body": "b", "gold": {"direction": "bullish", "magnitude": 1, '
                 '"confidence": "low", "reversibility": "unclear"}, '
                 '"gold_source": "test"}\n'
                 'NOT JSON\n')
    try:
        load_anchors(f)
        assert False, "Should have raised ValueError on malformed JSONL"
    except ValueError:
        pass


def test_load_anchors_empty_raises(tmp_path):
    f = tmp_path / "empty.jsonl"
    f.write_text("")
    try:
        load_anchors(f)
        assert False, "Should have raised ValueError on empty file"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# gate math: _score_predictions
# ---------------------------------------------------------------------------

def test_score_perfect_predictions_pass():
    anchors = [_make_anchor(direction="bullish"), _make_anchor(anchor_id="t2", direction="bearish")]
    preds = [
        {"direction": "bullish", "magnitude": 2, "confidence": "medium",
         "reversibility": "permanent",
         "quote_span": "agreed to acquire Acme Corp for $5B"},
        {"direction": "bearish", "magnitude": 2, "confidence": "medium",
         "reversibility": "permanent",
         "quote_span": "agreed to acquire Acme Corp for $5B"},
    ]
    scores = _score_predictions(anchors, preds)
    assert scores["field_agree_rate"] == 1.0
    assert scores["gate_pass"] is True
    assert scores["magnitude_band_rate"] == 1.0
    assert scores["confidence_band_rate"] == 1.0
    # Quote spans appear verbatim in body → verify rate = 1.0
    assert scores["quote_verify_rate"] == 1.0


def test_score_zero_direction_match_fails_gate():
    anchors = [_make_anchor(direction="bullish"), _make_anchor(anchor_id="t2", direction="bullish")]
    preds = [
        {"direction": "bearish", "magnitude": 1, "confidence": "low"},
        {"direction": "bearish", "magnitude": 1, "confidence": "low"},
    ]
    scores = _score_predictions(anchors, preds)
    assert scores["field_agree_rate"] == 0.0
    assert scores["gate_pass"] is False


def test_score_below_gate_threshold():
    # 0.80 < 0.85 gate
    anchors = [_make_anchor(direction="bullish")] * 10
    preds = [{"direction": "bullish", "magnitude": 2, "confidence": "medium"}] * 8 + \
            [{"direction": "bearish", "magnitude": 2, "confidence": "medium"}] * 2
    scores = _score_predictions(anchors, preds)
    assert abs(scores["field_agree_rate"] - 0.80) < 0.01
    assert scores["gate_pass"] is False


def test_score_at_gate_threshold():
    # exactly 0.85 → pass
    n = 20
    n_correct = 17  # 17/20 = 0.85
    anchors = [_make_anchor(direction="bullish")] * n
    preds = (
        [{"direction": "bullish", "magnitude": 2, "confidence": "medium"}] * n_correct
        + [{"direction": "bearish", "magnitude": 2, "confidence": "medium"}] * (n - n_correct)
    )
    scores = _score_predictions(anchors, preds)
    assert scores["gate_pass"] is True


def test_score_none_predictions_degrade_gracefully():
    anchors = [_make_anchor(direction="bullish")] * 3
    preds = [None, None, None]
    scores = _score_predictions(anchors, preds)
    assert scores["n_predicted"] == 0
    assert scores["field_agree_rate"] == 0.0
    assert scores["gate_pass"] is False


def test_score_magnitude_band_within_one():
    anchors = [_make_anchor(magnitude=2)]
    preds = [{"direction": "bullish", "magnitude": 3, "confidence": "medium"}]  # diff=1
    scores = _score_predictions(anchors, preds)
    assert scores["magnitude_band_rate"] == 1.0


def test_score_magnitude_band_outside_one():
    anchors = [_make_anchor(magnitude=0)]
    preds = [{"direction": "bullish", "magnitude": 3, "confidence": "medium"}]  # diff=3
    scores = _score_predictions(anchors, preds)
    assert scores["magnitude_band_rate"] == 0.0


# ---------------------------------------------------------------------------
# dry-run mode
# ---------------------------------------------------------------------------

def test_dry_run_passes_gate_with_real_anchors():
    anchor_path = Path(__file__).parent.parent / "data" / "drift_anchors" / "extraction_anchors.jsonl"
    if not anchor_path.exists():
        # Skip if anchors not built (CI without data)
        return
    anchors = load_anchors(anchor_path)
    scores = dry_run(anchors)
    assert scores["gate_pass"] is True
    assert scores["mode"] == "dry-run"
    assert scores["field_agree_rate"] == 1.0


def test_dry_run_synthetic():
    anchors = [_make_anchor(direction="bearish"), _make_anchor(anchor_id="t2", direction="neutral")]
    scores = dry_run(anchors)
    assert scores["gate_pass"] is True
    assert scores["field_agree_rate"] == 1.0
    assert scores["mode"] == "dry-run"


# ---------------------------------------------------------------------------
# news_llm off-state
# ---------------------------------------------------------------------------

def test_news_llm_off_in_config():
    """When news_llm.enabled=False in config, annotate() returns headlines unchanged."""
    from engine import news_llm
    import lib.config as cfg
    orig_load = cfg.load

    def patched_load():
        c = orig_load()
        c.setdefault("news_llm", {})["enabled"] = False
        return c

    cfg.load = patched_load
    try:
        headlines = [{"title": "Fed hikes rates", "quality": 0.8},
                     {"title": "Markets rally", "quality": 0.6}]
        result = news_llm.annotate(headlines)
        # Should return unchanged — no llm_importance added
        assert result is headlines
        assert "llm_importance" not in headlines[0]
    finally:
        cfg.load = orig_load


def test_news_llm_off_when_no_credentials():
    """annotate() is a no-op when no LLM provider credentials are present."""
    import os
    from engine import news_llm

    cred_keys = ["CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"]
    saved = {k: os.environ.pop(k, None) for k in cred_keys}
    try:
        headlines = [{"title": "Test headline", "quality": 0.5}]
        result = news_llm.annotate(headlines)
        assert result is headlines
        assert "llm_importance" not in headlines[0]
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# degraded-render fixtures: check emit from engine
# ---------------------------------------------------------------------------

def test_china_intel_analysis_emits_llm_synthesis_degraded_reason():
    """china_intel_analysis.analyze() must emit llm_synthesis_degraded_reason.

    We patch the internal disk-reader to return empty dicts so no live data is needed.
    """
    try:
        from engine import china_intel_analysis as cia
    except ImportError:
        return  # CI without the full engine

    # Patch _read to return {} for any path (no disk access needed).
    import unittest.mock as mock
    # NOTE (W5 integration): do NOT patch sys.modules here. A previous version used
    # `mock.patch.dict("sys.modules", {"engine.china_altdata": MagicMock()})`, which
    # snapshots-and-restores the WHOLE sys.modules dict. numpy's C extension cannot be
    # reloaded once evicted ("cannot load module more than once per process"), so the
    # restore left numpy=None process-wide and every later `import pandas` raised a
    # masked ImportError — silently breaking the whitehouse qledger adapter tests when
    # the suites ran in the same process. analyze() imports china_altdata lazily
    # (`from engine import china_altdata; china_altdata.convergence_map()`), so patch
    # the attribute on the real module instead — surgical and leak-free.
    from engine import china_altdata as _cad
    with mock.patch.object(cia, "_read", return_value={}), \
            mock.patch.object(_cad, "convergence_map", return_value={}):
        result = cia.analyze(prev=None)

    assert "llm_synthesis" in result, "llm_synthesis key missing from analyze() output"
    assert "llm_synthesis_degraded_reason" in result, (
        "llm_synthesis_degraded_reason key missing — degraded state not emitted explicitly"
    )
    assert result["llm_synthesis_degraded_reason"] == "not_wired"


def test_narrative_brain_degraded_artifact_has_degraded_reason():
    """The live narrative_brain.json artifact carries degraded_reason when no LLM ran."""
    artifact = Path(__file__).parent.parent / "site" / "basketdata" / "narrative_brain.json"
    if not artifact.exists():
        return
    b = json.loads(artifact.read_text())
    # Must be one of: no assessments → degraded_reason present, or non-empty assessments
    has_assessments = bool(b.get("assessments"))
    has_degraded = bool(b.get("degraded_reason"))
    # Either it has real assessments or it has a degraded_reason explaining why
    assert has_assessments or has_degraded, (
        "narrative_brain.json has neither assessments nor degraded_reason — "
        "degraded state is silent (violates spec §2.4)"
    )


# ---------------------------------------------------------------------------
# anchor file existence and distribution
# ---------------------------------------------------------------------------

def test_anchor_file_exists_and_has_50_records():
    anchor_path = Path(__file__).parent.parent / "data" / "drift_anchors" / "extraction_anchors.jsonl"
    if not anchor_path.exists():
        return  # skip in CI without data
    anchors = load_anchors(anchor_path)
    assert len(anchors) == 50, f"Expected 50 anchors, got {len(anchors)}"


def test_anchor_file_has_at_least_5_bearish():
    anchor_path = Path(__file__).parent.parent / "data" / "drift_anchors" / "extraction_anchors.jsonl"
    if not anchor_path.exists():
        return
    anchors = load_anchors(anchor_path)
    bearish_n = sum(1 for a in anchors if a["gold"]["direction"] == "bearish")
    assert bearish_n >= 5, f"Expected ≥5 bearish anchors, got {bearish_n}"


def test_anchor_file_has_mixed_source_lanes():
    anchor_path = Path(__file__).parent.parent / "data" / "drift_anchors" / "extraction_anchors.jsonl"
    if not anchor_path.exists():
        return
    anchors = load_anchors(anchor_path)
    lanes = {a["source_lane"] for a in anchors}
    assert len(lanes) >= 2, f"Expected ≥2 source lanes, got: {lanes}"


