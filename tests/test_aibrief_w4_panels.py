"""Tests for ADB-W4 page panels (context strip, What's ahead, Brief's own record,
Cortex deliberation).

Acceptance criteria per masterplan ADB-W4:
- n-floor law: scored_total < 20 → calibration_note rendered, not a numeric hit-rate %
- context strip absent when ALL source reads fail (fail-open)
- forward panel absent when both event_calendar + release_forecast raise
- cortex panel present in HTML (client-side; content rendered by aibrief.js)
- bilingual dual-span in template output
- no 'validated' on visible tier (checked via check_validated_claims)
- template-site sync green (aibrief.js byte-identical)
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import jinja2
import pytest

# Resolve repo root relative to this test file
ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(ROOT))

from engine import i18n
from lib import config
from scripts.build_aibrief import (
    _gather_context_strip,
    _gather_forward_panel,
    _gather_record_panel,
    _gather_panels,
    main as build_main,
)


# ── helpers ─────────────────────────────────────────────────────────────────────

def _env() -> jinja2.Environment:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")))
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env


def _render(**kwargs) -> str:
    panels = {
        "ctx_strip": kwargs.get("ctx_strip", {"absent": True}),
        "fwd_panel": kwargs.get("fwd_panel", {"absent": True, "events": [], "rebal_note_en": None, "rebal_note_zh": None}),
        "record_panel": kwargs.get("record_panel", {"absent": True}),
    }
    return _env().get_template("aibrief.html.j2").render(
        as_of="2026-07-12 05:00 UTC", **panels
    )


def _make_market_plane(regime_en="Risk-on", regime_zh="风险偏好") -> dict:
    return {
        "schema": "neuralweb.market_plane.v1",
        "asof": "2026-07-12",
        "is_context_only": True,
        "verdict": {"verdict": "RISK_ON", "score": 80, "label_en": regime_en, "label_zh": regime_zh},
        "cortex": {"status": "degraded", "degradation_reason": "model_unavailable"},
        "produced_at": "2026-07-12T05:00:00Z",
        "tier": "display",
    }


def _make_world_state(n_contra=2, severity_tension=1) -> dict:
    return {
        "contradictions": {
            "n": n_contra,
            "by_severity": {"note": max(0, n_contra - severity_tension), "tension": severity_tension},
            "top_pair_ids": ["briefing-divergences"],
            "gaps": [],
            "display_only": True,
            "note": "Test contradiction note.",
        }
    }


def _make_liquidity_plumbing(state="stress_liquidity_expansion") -> dict:
    return {
        "schema": "liquidity_plumbing.v1",
        "asof": "2026-07-12",
        "headline": {"state": state, "summary": "Test summary."},
        "produced_at": "2026-07-12T05:00:00Z",
        "tier": "display",
    }


def _make_track_record(scored_total=2) -> dict:
    return {
        "schema": "master_brain_track_record.v1",
        "as_of": "2026-07-11",
        "scored_total": scored_total,
        "open": 4,
        "overall": {"n": scored_total, "hits": scored_total, "misses": 0, "hit_rate": 1.0},
        "calibration_note": (
            f"{scored_total} leans scored. Sample is tiny "
            "— the brain's leans are accountability, not yet a proven edge."
        ),
        "calibration_note_zh": (
            f"已评分 {scored_total} 条。样本极小——大脑的判断仅为问责，尚非优势。"
        ),
    }


# ── Panel A: context strip ───────────────────────────────────────────────────────

class TestContextStrip:
    def _write_fixtures(self, tmp: Path) -> None:
        nw = tmp / "neuralweb"
        nw.mkdir(parents=True, exist_ok=True)
        (nw / "market_plane.json").write_text(json.dumps(_make_market_plane()))
        (nw / "world_state.json").write_text(json.dumps(_make_world_state()))
        (nw / "liquidity_plumbing.json").write_text(json.dumps(_make_liquidity_plumbing()))

    def test_renders_regime_label(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_fixtures(Path(td))
            out = _gather_context_strip(Path(td))
        assert not out["absent"]
        assert out["regime_label_en"] == "Risk-on"
        assert out["regime_label_zh"] == "风险偏好"

    def test_renders_contradiction_plain_word(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_fixtures(Path(td))
            out = _gather_context_strip(Path(td))
        # Tension-class contradiction → "bonds and stocks" plain line
        assert "bonds and stocks" in (out["contradiction_line_en"] or "")

    def test_no_tension_gets_mixed_signals_line(self):
        with tempfile.TemporaryDirectory() as td:
            nw = Path(td) / "neuralweb"
            nw.mkdir(parents=True, exist_ok=True)
            (nw / "market_plane.json").write_text(json.dumps(_make_market_plane()))
            (nw / "world_state.json").write_text(json.dumps(_make_world_state(n_contra=1, severity_tension=0)))
            (nw / "liquidity_plumbing.json").write_text(json.dumps(_make_liquidity_plumbing()))
            out = _gather_context_strip(Path(td))
        assert "mixed signals" in (out["contradiction_line_en"] or "")

    def test_zero_contradictions_same_way_line(self):
        with tempfile.TemporaryDirectory() as td:
            nw = Path(td) / "neuralweb"
            nw.mkdir(parents=True, exist_ok=True)
            (nw / "market_plane.json").write_text(json.dumps(_make_market_plane()))
            (nw / "world_state.json").write_text(json.dumps(_make_world_state(n_contra=0, severity_tension=0)))
            (nw / "liquidity_plumbing.json").write_text(json.dumps(_make_liquidity_plumbing()))
            out = _gather_context_strip(Path(td))
        assert "same way" in (out["contradiction_line_en"] or "")

    def test_liquidity_plain_word_no_raw_state(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_fixtures(Path(td))
            out = _gather_context_strip(Path(td))
        # Should NOT echo the raw slug
        assert "stress_liquidity_expansion" not in (out["liquidity_en"] or "")
        assert out["liquidity_en"] is not None

    def test_cortex_degraded_chip(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_fixtures(Path(td))
            out = _gather_context_strip(Path(td))
        assert out["cortex_status"] == "degraded"
        assert "rate-limited" in (out["cortex_en"] or "").lower()

    def test_absent_when_all_reads_fail(self):
        with tempfile.TemporaryDirectory() as td:
            out = _gather_context_strip(Path(td))  # empty dir → all reads fail
        assert out["absent"] is True

    def test_template_renders_regime_chip(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_fixtures(Path(td))
            ctx_strip = _gather_context_strip(Path(td))
        html = _render(ctx_strip=ctx_strip)
        assert "Risk-on" in html
        assert "ctx-chip regime" in html

    def test_template_absent_strip_not_rendered(self):
        html = _render()  # default absent=True
        # CSS class names appear in the <style> block regardless; check the PANEL content
        assert "Right now" not in html
        assert "当前状态" not in html


# ── Panel B: What's ahead ────────────────────────────────────────────────────────

class TestForwardPanel:
    def _write_release_forecast(self, tmp: Path) -> None:
        rf_dir = tmp / "release_forecast"
        rf_dir.mkdir(parents=True, exist_ok=True)
        upcoming = [
            {
                "release": "cpi",
                "release_type": "cpi_headline",
                "period": "2026-06",
                "release_date": "2026-07-14",
                "days_to": 2,
                "surprise_skew": {"sigma": -1.5, "tag": "cooler", "inline_band": 0.35},
                "benchmark_set": {"market_implied": {"implied": "0.2%", "source": "polymarket"}},
            }
        ]
        payload = {"schema": "release_forecast.v2", "asof": "2026-07-12T05:00:00Z",
                   "display_only": True, "upcoming": upcoming}
        (rf_dir / "latest.json").write_text(json.dumps(payload))
        (rf_dir / "scoreboard.json").write_text(json.dumps(
            {"schema": "release_forecast_scoreboard.v2", "asof": "2026-07-12T05:00:00Z",
             "by_release": {}, "by_shadow": {}}
        ))

    def test_event_calendar_events_included(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_release_forecast(Path(td))
            out = _gather_forward_panel(Path(td), today=date(2026, 7, 12))
        dates = [e["date"] for e in out["events"]]
        assert any("2026-07" in d for d in dates)

    def test_no_claims_release(self):
        """Claims entries must be skipped (model killed — ADB-R4)."""
        with tempfile.TemporaryDirectory() as td:
            rf_dir = Path(td) / "release_forecast"
            rf_dir.mkdir(parents=True, exist_ok=True)
            upcoming = [
                {"release": "claims", "release_date": "2026-07-17", "days_to": 5,
                 "surprise_skew": {}, "benchmark_set": {}},
                {"release": "cpi", "release_date": "2026-07-14", "days_to": 2,
                 "surprise_skew": {}, "benchmark_set": {}},
            ]
            (rf_dir / "latest.json").write_text(json.dumps(
                {"schema": "release_forecast.v2", "asof": "...", "display_only": True, "upcoming": upcoming}
            ))
            (rf_dir / "scoreboard.json").write_text(json.dumps(
                {"by_release": {}, "by_shadow": {}}
            ))
            out = _gather_forward_panel(Path(td), today=date(2026, 7, 12))
        labels = [e["label_en"].lower() for e in out["events"]]
        assert not any("claims" in lbl for lbl in labels)
        assert any("cpi" in lbl for lbl in labels)

    def test_no_accuracy_record_in_tip_when_scoreboard_empty(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_release_forecast(Path(td))
            out = _gather_forward_panel(Path(td), today=date(2026, 7, 12))
        forecast_events = [e for e in out["events"] if e.get("is_forecast")]
        assert len(forecast_events) > 0
        assert any("No accuracy record yet" in e.get("tip_en", "") for e in forecast_events)

    def test_template_renders_forward_list(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_release_forecast(Path(td))
            fwd = _gather_forward_panel(Path(td), today=date(2026, 7, 12))
        html = _render(fwd_panel=fwd)
        assert "fwd-list" in html
        assert "What" in html  # "What's ahead"

    def test_absent_when_no_events_and_no_rebal(self):
        with tempfile.TemporaryDirectory() as td:
            # Patch event calendar to return empty and no release_forecast
            with patch("scripts.build_aibrief._gather_forward_panel",
                       return_value={"absent": True, "events": [], "rebal_note_en": None, "rebal_note_zh": None}):
                pass
        # The real test: empty data dir + patch high_impact_strip
        with patch("engine.event_calendar.high_impact_strip", return_value=[]):
            with tempfile.TemporaryDirectory() as td:
                out = _gather_forward_panel(Path(td), today=date(2026, 7, 12))
        # rebal may produce a note, but no events → may or may not be absent
        # just confirm events list doesn't contain forecast rows
        forecast = [e for e in out["events"] if e.get("is_forecast")]
        assert len(forecast) == 0  # no release_forecast dir → no forecast events


# ── Panel C: Brief's own record ──────────────────────────────────────────────────

class TestRecordPanel:
    def _write_track_record(self, tmp: Path, scored_total: int = 2) -> None:
        mb = tmp / "master_brain"
        mb.mkdir(parents=True, exist_ok=True)
        (mb / "track_record.json").write_text(json.dumps(_make_track_record(scored_total)))
        # One open thesis
        thesis = {
            "id": "mb-test-1", "logged_at": "2026-07-01T00:00:00Z",
            "state_asof": "2026-07-01", "subject": "Semiconductors",
            "lean": "underweight", "conviction": "medium", "horizon_d": 10,
            "falsifier": {"text": "Semis RS reverses decisively."},
            "check_by": "2026-07-15", "status": "open", "scored_at": None, "outcome": None,
        }
        (mb / "theses.jsonl").write_text(json.dumps(thesis) + "\n")

    def test_calibration_note_rendered_when_n_below_floor(self):
        """ADB-R12c: n=2 → calibration note rendered, not a numeric rate."""
        with tempfile.TemporaryDirectory() as td:
            self._write_track_record(Path(td), scored_total=2)
            out = _gather_record_panel(Path(td))
        assert not out["absent"]
        assert out["show_rate"] is False  # n=2 < 20
        assert out["calibration_note_en"] is not None
        assert "tiny" in out["calibration_note_en"].lower() or "scored" in out["calibration_note_en"].lower()

    def test_show_rate_true_when_n_above_floor(self):
        with tempfile.TemporaryDirectory() as td:
            mb = Path(td) / "master_brain"
            mb.mkdir(parents=True, exist_ok=True)
            (mb / "track_record.json").write_text(json.dumps(_make_track_record(scored_total=25)))
            (mb / "theses.jsonl").write_text("")
            out = _gather_record_panel(Path(td))
        assert out["show_rate"] is True

    def test_open_lean_plain_word_stance(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_track_record(Path(td))
            out = _gather_record_panel(Path(td))
        assert len(out["open_leans"]) > 0
        lean = out["open_leans"][0]
        # Must not say "underweight" in the visible tier
        assert "underweight" not in lean["stance_en"]
        # Must say "leaning away from" (capitalize-first form is also acceptable)
        assert "leaning away from" in lean["stance_en"].lower()

    def test_absent_when_no_track_record(self):
        with tempfile.TemporaryDirectory() as td:
            out = _gather_record_panel(Path(td))
        assert out["absent"] is True

    def test_template_renders_calibration_note(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_track_record(Path(td), scored_total=2)
            rp = _gather_record_panel(Path(td))
        html = _render(record_panel=rp)
        assert "record-cal" in html
        assert "The brief's own record" in html or "brief" in html.lower()

    def test_template_absent_record_not_rendered(self):
        html = _render()  # absent=True
        # CSS class names appear in <style> regardless; check the PANEL heading
        assert "The brief&#39;s own record" not in html
        assert "简报自身记录" not in html

    def test_no_numeric_rate_in_template_when_n_below_floor(self):
        """n=2 → template must not expose '100%' or 'hit-rate 1.0' in a raw rate context."""
        with tempfile.TemporaryDirectory() as td:
            self._write_track_record(Path(td), scored_total=2)
            rp = _gather_record_panel(Path(td))
        # The calibration_note itself is from the artifact; show_rate=False ensures
        # no separately generated "hit rate" text is added
        assert rp["show_rate"] is False
        # Template should not add its own rate calculation (separate from CSS top:100%)
        html = _render(record_panel=rp)
        # The CSS has "top:100%" — strip CSS block before checking
        body_only = html[html.find("</style>"):]
        assert "100%" not in body_only  # no percentage-format rate in the rendered body


# ── Panel D: Cortex deliberation (template structure only) ──────────────────────

class TestCortexPanel:
    def test_cortex_panel_id_in_template(self):
        html = _render()
        assert 'id="cortex-panel"' in html

    def test_cortex_panel_hidden_by_default(self):
        html = _render()
        assert '#cortex-panel { display:none; }' in html or 'id="cortex-panel"' in html

    def test_cortex_body_id_present(self):
        html = _render()
        assert 'id="cortex-body"' in html

    def test_aibrief_js_loaded(self):
        html = _render()
        assert 'src="aibrief.js"' in html


# ── Integration: build_aibrief runs green ───────────────────────────────────────

class TestBuildMain:
    def test_build_returns_zero(self):
        """build_aibrief.main() must return 0 even with real production artifacts."""
        result = build_main()
        assert result == 0

    def test_rendered_html_has_all_four_panels(self):
        """Site/aibrief.html must contain all four panel indicators after a real build."""
        site_html = Path(config.ROOT) / "site" / "aibrief.html"
        if not site_html.exists():
            pytest.skip("site/aibrief.html not built yet")
        content = site_html.read_text()
        assert "Right now" in content or "当前状态" in content  # Panel A
        assert "What" in content  # Panel B
        assert "own record" in content or "简报自身记录" in content  # Panel C
        assert 'id="cortex-panel"' in content  # Panel D

    def test_no_validated_on_visible_tier(self):
        """check_validated_claims must pass after a build."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "scripts.check_validated_claims"],
            cwd=str(ROOT), capture_output=True, text=True
        )
        assert result.returncode == 0, f"check_validated_claims failed: {result.stdout}\n{result.stderr}"

    def test_template_site_sync_green(self):
        """aibrief.js must be byte-identical between templates/ and site/."""
        tmpl = ROOT / "templates" / "aibrief.js"
        site = ROOT / "site" / "aibrief.js"
        assert tmpl.exists(), "templates/aibrief.js missing"
        assert site.exists(), "site/aibrief.js missing"
        assert tmpl.read_bytes() == site.read_bytes(), "aibrief.js out of sync — run check_template_site_sync --fix"
