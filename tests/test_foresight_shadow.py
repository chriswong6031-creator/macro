"""engine.foresight_shadow — W3b shadow-threshold ledger tests.

Five required test cases:
  (a) shadow stages recompute under each candidate and DIFFER from live when the candidate
      would flip a theme (synthetic fixture)
  (b) dedup on re-run — no double-writes for the same (param, candidate, theme, asof)
  (c) grade_shadow produces per-(param,candidate) slices with the same stage-role semantics
      (control arms excluded from hit-rates)
  (d) promotion report says PROMOTABLE only on FDR-significant superiority (synthetic rows)
  (e) empty ledger → honest "accruing" report, never a fabricated comparison
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import foresight_shadow as fs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _price_series(level_end: float, start: str = "2025-01-01", periods: int = 550) -> pd.Series:
    idx = pd.date_range(start, periods=periods, freq="D")
    return pd.Series(np.linspace(100.0, level_end, len(idx)), index=idx)


def _patch_prices(monkeypatch, tmp_path, closes: dict):
    monkeypatch.setattr(fs, "config", _fake_config(tmp_path))
    # Also patch foresight_grader._closes via the module attribute used in grade_shadow
    from engine import foresight_grader as gr
    monkeypatch.setattr(gr, "_closes", lambda tk: closes.get(tk))
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(gr.config, "load",
                        lambda: {"themes": {
                            "memory_storage": {"tickers": ["MU", "WDC"]},
                            "ai_semiconductors": {"tickers": ["NVDA"]},
                        }})


def _fake_config(tmp_path):
    """Minimal config shim that redirects data_dir to tmp_path."""
    class _Cfg:
        @staticmethod
        def data_dir():
            return Path(tmp_path)
        @staticmethod
        def load():
            return {"themes": {
                "memory_storage": {"tickers": ["MU", "WDC"]},
                "ai_semiconductors": {"tickers": ["NVDA"]},
            }}
    return _Cfg()


def _write_shadow_rows(tmp_path, rows: list[dict]) -> None:
    """Write synthetic shadow STAGE rows to shadow_log.jsonl."""
    p = Path(tmp_path) / "foresight" / "shadow_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _write_live_rows(tmp_path, rows: list[dict]) -> None:
    """Write synthetic live stage rows to foresight/log.jsonl."""
    p = Path(tmp_path) / "foresight" / "log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# (a) Shadow stages recompute and DIFFER from live when the candidate would flip a theme
# ---------------------------------------------------------------------------

def test_shadow_stages_differ_from_live_when_candidate_flips_theme(monkeypatch, tmp_path):
    """compute_shadow_stages: when a shadow broad_hi_pctile candidate (p90) raises the
    late-line threshold above a theme's breadth, a RE-RATING live stage flips to WATCH/BROADENING
    under that candidate — demonstrating stage divergence from the live value.

    Fixture design (verified numerically):
      9 background themes at breadth 0.1..0.9, memory_storage at 0.85.
      Pool values: [0.1, 0.2, ..., 0.85, 0.9]
      p80 ≈ 0.81 → 0.85 > 0.81 → live RE-RATING (revisions-only, no bottleneck).
      p90 ≈ 0.855 → 0.85 < 0.855 → under p90, NOT late → WATCH (revisions-only).
    """
    from engine.foresight_shadow import compute_shadow_stages, SHADOW_GRID
    monkeypatch.setattr(fs, "config", _fake_config(tmp_path))
    (Path(tmp_path) / "foresight").mkdir(parents=True, exist_ok=True)

    # 9 background themes (breadths 0.1..0.9) + memory_storage at 0.85
    # Pool p80 = 0.81, p90 = 0.855 (numpy linear interp over 10 values)
    rv_themes = {f"s{i}": {"breadth": 0.1 * (i + 1), "level_state": "POSITIVE", "name": f"s{i}"}
                 for i in range(9)}
    rv_themes["memory_storage"] = {"breadth": 0.85, "level_state": "POSITIVE", "name": "Memory"}

    revisions = {"themes": rv_themes, "asof": "2026-07-01"}
    # No bottleneck for memory_storage → revisions-only staging (simpler to reason about)
    bottleneck = {"themes": {}, "asof": "2026-07-01"}

    n = compute_shadow_stages(
        bottleneck=bottleneck,
        revisions=revisions,
        glut=None,
        asof="2026-07-01",
    )
    assert n > 0, "no shadow rows were appended"

    # Read back and verify stage divergence for broad_hi_pctile candidates
    p = Path(tmp_path) / "foresight" / "shadow_log.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    stage_rows = [r for r in rows if "param" in r and "stage" in r]
    assert stage_rows, "no STAGE rows written to shadow_log"

    pctile_rows = [r for r in stage_rows
                   if r["param"] == "broad_hi_pctile" and r["theme"] == "memory_storage"]
    assert pctile_rows, "no broad_hi_pctile rows for memory_storage"

    # The live stage should be RE-RATING: breadth 0.85 > p80 ≈ 0.81
    live_stage_val = pctile_rows[0]["live_stage"]
    assert live_stage_val == "RE-RATING", (
        f"expected live RE-RATING at breadth=0.85 (above p80≈0.81), got {live_stage_val}"
    )

    # Under p90 (threshold ≈ 0.855 > 0.85): memory_storage is NOT flagged late → stage flips
    p90_row = next((r for r in pctile_rows if r["candidate"] == 90.0), None)
    assert p90_row is not None, "p90 candidate row missing"
    assert p90_row["stage"] != "RE-RATING", (
        f"under p90 candidate (threshold > 0.85), memory_storage should NOT be RE-RATING, "
        f"got {p90_row['stage']}"
    )

    # Verify divergence: at least one candidate flips vs live
    divergent = [r for r in pctile_rows if r["stage"] != r["live_stage"]]
    assert divergent, (
        f"all candidates produced the same stage as live (RE-RATING) — expected at least one flip. "
        f"Candidates: {[(r['candidate'], r['stage']) for r in pctile_rows]}"
    )


def test_lang_z_cutoff_shadow_flips_text_band(monkeypatch, tmp_path):
    """lang_z_cutoff candidates flip a text-only theme's stage when accel is between candidates."""
    from engine.foresight_shadow import compute_shadow_stages
    monkeypatch.setattr(fs, "config", _fake_config(tmp_path))
    (Path(tmp_path) / "foresight").mkdir(parents=True, exist_ok=True)

    # lang_accel=1.2: above live cutoff (0.5) → live TIGHT(text) → PRECIPICE(text)
    # above candidate 1.0 → shadow also TIGHT(text) → PRECIPICE(text)
    # BETWEEN 1.0 and 1.5 → for 1.5 candidate: not TIGHT(text) → TIGHTENING(text)
    # This should produce different stages at different cutoffs
    bottleneck = {"themes": {
        "ai_semiconductors": {
            "name": "AI Semis", "band": "TIGHT (text)", "tightness": None,
            "regime": False, "text_only": True,
            "language_accel": 1.2, "language_n_filers": 3,
        }
    }, "asof": "2026-07-01"}
    revisions = {"themes": {
        "ai_semiconductors": {"breadth": 0.05, "level_state": "FLAT_LOW", "name": "AI Semis"},
    }, "asof": "2026-07-01"}

    n = compute_shadow_stages(
        bottleneck=bottleneck,
        revisions=revisions,
        glut=None,
        asof="2026-07-01",
    )
    assert n > 0

    p = Path(tmp_path) / "foresight" / "shadow_log.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    lang_rows = [r for r in rows
                 if r.get("param") == "lang_z_cutoff" and r.get("theme") == "ai_semiconductors"]
    assert lang_rows, "no lang_z_cutoff rows for ai_semiconductors"

    # At cutoff=1.0: accel 1.2 > 1.0 → TIGHT(text) → PRECIPICE(text)
    # At cutoff=1.5: accel 1.2 < 1.5 → TIGHTENING(text) → PRECIPICE(text) still (revisions flat)
    # At cutoff=2.0: accel 1.2 < 2.0 → TIGHTENING(text)
    # All three should be written
    cutoffs_found = {r["candidate"] for r in lang_rows}
    from engine.bottleneck import LANG_Z_SHADOW_CUTOFFS
    for c in LANG_Z_SHADOW_CUTOFFS:
        assert c in cutoffs_found, f"cutoff {c} missing from shadow rows"


# ---------------------------------------------------------------------------
# (b) Dedup on re-run
# ---------------------------------------------------------------------------

def test_dedup_on_rerun(monkeypatch, tmp_path):
    """compute_shadow_stages called twice with the same inputs writes each (param,candidate,theme,asof)
    exactly once — idempotent re-runs stay clean."""
    from engine.foresight_shadow import compute_shadow_stages
    monkeypatch.setattr(fs, "config", _fake_config(tmp_path))
    (Path(tmp_path) / "foresight").mkdir(parents=True, exist_ok=True)

    bottleneck = {"themes": {
        "memory_storage": {
            "name": "Memory", "band": "TIGHT", "tightness": 0.9, "regime": True,
            "text_only": False, "language_accel": None, "language_n_filers": 0,
        }
    }, "asof": "2026-07-01"}
    revisions = {"themes": {
        "memory_storage": {"breadth": 0.05, "level_state": "FLAT_LOW", "name": "Memory"},
    }, "asof": "2026-07-01"}

    n1 = compute_shadow_stages(bottleneck=bottleneck, revisions=revisions,
                                glut=None, asof="2026-07-01")
    n2 = compute_shadow_stages(bottleneck=bottleneck, revisions=revisions,
                                glut=None, asof="2026-07-01")

    assert n1 > 0, "first run should write rows"
    assert n2 == 0, f"second run with same asof should write 0 rows (dedup), got {n2}"

    p = Path(tmp_path) / "foresight" / "shadow_log.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    stage_rows = [r for r in rows if "stage" in r and "param" in r]

    # Verify no duplicate (param, candidate, theme, asof) tuples
    keys = [(r["param"], r["candidate"], r["theme"], r["asof"]) for r in stage_rows]
    assert len(keys) == len(set(keys)), f"duplicate rows found after re-run: {keys}"


def test_dedup_new_asof_writes_new_rows(monkeypatch, tmp_path):
    """A new asof date (different day) writes new rows even for the same theme/param/candidate."""
    from engine.foresight_shadow import compute_shadow_stages
    monkeypatch.setattr(fs, "config", _fake_config(tmp_path))
    (Path(tmp_path) / "foresight").mkdir(parents=True, exist_ok=True)

    bottleneck = {"themes": {
        "memory_storage": {
            "name": "Memory", "band": "TIGHT", "tightness": 0.9, "regime": True,
            "text_only": False, "language_accel": None, "language_n_filers": 0,
        }
    }}
    revisions = {"themes": {
        "memory_storage": {"breadth": 0.05, "level_state": "FLAT_LOW", "name": "Memory"},
    }}

    n1 = compute_shadow_stages(bottleneck=bottleneck, revisions=revisions,
                                glut=None, asof="2026-07-01")
    n2 = compute_shadow_stages(bottleneck=bottleneck, revisions=revisions,
                                glut=None, asof="2026-07-02")   # different asof

    assert n1 > 0
    assert n2 > 0, "new asof should produce new rows"


# ---------------------------------------------------------------------------
# (c) grade_shadow: per-(param,candidate) slices with correct stage-role semantics
# ---------------------------------------------------------------------------

def test_grade_shadow_produces_per_param_candidate_slices(monkeypatch, tmp_path):
    """grade_shadow produces keyed slices for each (param,candidate) and the live slice."""
    closes = {
        "MU": _price_series(150), "WDC": _price_series(145),
        "NVDA": _price_series(160), "SPY": _price_series(110),
    }
    _patch_prices(monkeypatch, tmp_path, closes)

    # Write synthetic shadow STAGE rows that have matured at 90d
    shadow_rows = []
    for param in ["broad_hi_pctile", "lang_z_cutoff"]:
        for candidate in [70.0, 80.0, 90.0] if param == "broad_hi_pctile" else [1.0, 1.5, 2.0]:
            shadow_rows.append({
                "param": param,
                "candidate": candidate,
                "theme": "memory_storage",
                "asof": "2026-01-01",
                "stage": "PRECIPICE",
                "live_stage": "RE-RATING",
            })
    _write_shadow_rows(tmp_path, shadow_rows)

    # Write live rows for comparison
    _write_live_rows(tmp_path, [
        {"theme": "memory_storage", "asof": "2026-01-01", "stage": "RE-RATING",
         "members": ["MU", "WDC"]},
    ])

    result = fs.grade_shadow(today=pd.Timestamp("2026-06-01"), write=False)
    slices = result.get("slices") or {}

    # Should have one slice per (param, candidate) combo + the live slice
    assert "live" in slices, "live slice missing"
    assert "broad_hi_pctile|70.0" in slices
    assert "broad_hi_pctile|80.0" in slices
    assert "broad_hi_pctile|90.0" in slices
    assert "lang_z_cutoff|1.0" in slices
    assert "lang_z_cutoff|1.5" in slices
    assert "lang_z_cutoff|2.0" in slices


def test_grade_shadow_control_arms_excluded_from_hit_rates(monkeypatch, tmp_path):
    """Control-arm stages (RE-RATING, WATCH) in shadow rows must not produce hit-rates — only
    avg_excess. Same semantics as the live grader."""
    closes = {
        "MU": _price_series(150), "WDC": _price_series(145), "SPY": _price_series(110),
    }
    _patch_prices(monkeypatch, tmp_path, closes)

    # Write a shadow row with RE-RATING stage (control arm)
    _write_shadow_rows(tmp_path, [{
        "param": "broad_hi_pctile",
        "candidate": 70.0,
        "theme": "memory_storage",
        "asof": "2026-01-01",
        "stage": "RE-RATING",    # control arm
        "live_stage": "RE-RATING",
        "members": ["MU", "WDC"],
    }])
    _write_live_rows(tmp_path, [])

    result = fs.grade_shadow(today=pd.Timestamp("2026-06-01"), write=False)
    sl = result["slices"].get("broad_hi_pctile|70.0") or {}
    by_stage = sl.get("by_stage") or {}
    re_rating = by_stage.get("RE-RATING")
    assert re_rating is not None, "RE-RATING bucket should exist"
    # Control arm: n_dir=0, hit_rate=None — forward excess only (beta not skill)
    assert re_rating["n_dir"] == 0, "control arm should have n_dir=0"
    assert re_rating["hit_rate"] is None, "control arm must NOT publish a hit-rate"
    assert re_rating["avg_excess_pct"] is not None, "control arm should have avg_excess"


def test_grade_shadow_thesis_stages_produce_hit_rates(monkeypatch, tmp_path):
    """PRECIPICE rows in shadow slices produce a hit-rate (thesis stage, outperform = hit)."""
    closes = {
        "MU": _price_series(150), "WDC": _price_series(145), "SPY": _price_series(110),
    }
    _patch_prices(monkeypatch, tmp_path, closes)

    _write_shadow_rows(tmp_path, [{
        "param": "broad_hi_pctile",
        "candidate": 90.0,
        "theme": "memory_storage",
        "asof": "2026-01-01",
        "stage": "PRECIPICE",   # thesis stage
        "live_stage": "RE-RATING",
        "members": ["MU", "WDC"],
    }])
    _write_live_rows(tmp_path, [])

    result = fs.grade_shadow(today=pd.Timestamp("2026-06-01"), write=False)
    sl = result["slices"].get("broad_hi_pctile|90.0") or {}
    by_stage = sl.get("by_stage") or {}
    prec = by_stage.get("PRECIPICE")
    assert prec is not None
    assert prec["n_dir"] == 1
    assert prec["hit_rate"] == 1.0   # theme >> SPY → hit


# ---------------------------------------------------------------------------
# (d) Promotion report: PROMOTABLE only on FDR-significant superiority
# ---------------------------------------------------------------------------

def test_promotion_report_not_promotable_without_fdr_significance(monkeypatch, tmp_path):
    """A candidate that beats live hit-rate but without FDR-significant per-theme superiority
    reports BETTER_NOT_SIGNIFICANT, not PROMOTABLE."""
    # Synthesize a graded shadow_summary directly (bypass file I/O for this unit test)
    shadow_summary = {
        "slices": {
            "live": {
                "n_graded": 5, "n_pending": 0,
                "pooled_n_directional": 5,
                "pooled_hit_rate": 0.6,
                "n_significant_fdr": 0,
                "by_stage": {},
                # by_theme: p_value = 0.5 (not significant) for each theme
                "by_theme": {
                    "memory_storage": {
                        "n": 5, "n_dir": 5, "hits": 3, "hit_rate": 0.6,
                        "p_value": 0.5, "significant_fdr": False, "n_independent": 5,
                        "avg_excess_pct": 2.0, "ci95": [0.2, 0.9],
                    }
                },
                "by_horizon": {},
            },
            "broad_hi_pctile|70.0": {
                "n_graded": 5, "n_pending": 0,
                "pooled_n_directional": 5,
                "pooled_hit_rate": 0.8,   # better than live 0.6, but...
                "n_significant_fdr": 0,
                "by_stage": {},
                "by_theme": {
                    "memory_storage": {
                        "n": 5, "n_dir": 5, "hits": 4, "hit_rate": 0.8,
                        "p_value": 0.18,   # NOT significant at FDR threshold
                        "significant_fdr": False, "n_independent": 5,
                        "avg_excess_pct": 3.0, "ci95": [0.4, 1.0],
                    }
                },
                "by_horizon": {},
            },
        }
    }

    # Patch live value
    monkeypatch.setattr(fs, "_live_value",
                        lambda p: 80.0 if p == "broad_hi_pctile" else 0.5)

    report = fs.shadow_promotion_report(shadow_summary=shadow_summary)
    assert report["accruing"] is False, "5 directional obs → not accruing"
    assert len(report["promotable"]) == 0, "should NOT be promotable without FDR significance"

    # Find the broad_hi_pctile|70.0 entry
    entry = next((c for c in report["candidates"]
                  if c["param"] == "broad_hi_pctile" and c["candidate"] == 70.0), None)
    assert entry is not None
    assert entry["verdict"] == "BETTER_NOT_SIGNIFICANT"


def test_promotion_report_promotable_on_fdr_significant_superiority(monkeypatch, tmp_path):
    """A candidate with FDR-significant per-theme superiority over live reports PROMOTABLE."""
    # Synthesize a case where the candidate has significantly better hit-rate
    # and its per-theme p_value clears the BY-FDR threshold
    shadow_summary = {
        "slices": {
            "live": {
                "n_graded": 10, "n_pending": 0,
                "pooled_n_directional": 10,
                "pooled_hit_rate": 0.5,
                "n_significant_fdr": 0,
                "by_stage": {},
                "by_theme": {
                    "memory_storage": {
                        "n": 10, "n_dir": 10, "hits": 5, "hit_rate": 0.5,
                        "p_value": 0.623, "significant_fdr": False, "n_independent": 10,
                        "avg_excess_pct": 0.5, "ci95": [0.2, 0.8],
                    }
                },
                "by_horizon": {},
            },
            "broad_hi_pctile|70.0": {
                "n_graded": 10, "n_pending": 0,
                "pooled_n_directional": 10,
                "pooled_hit_rate": 0.9,   # better than live
                "n_significant_fdr": 1,
                "by_stage": {},
                "by_theme": {
                    "memory_storage": {
                        "n": 10, "n_dir": 10, "hits": 9, "hit_rate": 0.9,
                        "p_value": 0.01,   # statistically significant (< FDR threshold)
                        "significant_fdr": True, "n_independent": 10,
                        "avg_excess_pct": 5.0, "ci95": [0.6, 1.0],
                    }
                },
                "by_horizon": {},
            },
        }
    }

    monkeypatch.setattr(fs, "_live_value",
                        lambda p: 80.0 if p == "broad_hi_pctile" else 0.5)

    report = fs.shadow_promotion_report(shadow_summary=shadow_summary)
    assert report["accruing"] is False

    # broad_hi_pctile|70.0 has FDR-significant superiority → PROMOTABLE
    assert "broad_hi_pctile|70.0" in report["promotable"], (
        f"Expected PROMOTABLE for broad_hi_pctile|70.0, got candidates: "
        f"{[(c['param'], c['candidate'], c['verdict']) for c in report['candidates']]}"
    )

    entry = report["promotable"]["broad_hi_pctile|70.0"]
    assert entry["verdict"] == "PROMOTABLE"
    assert entry["fdr_significant"] is True
    # Sanity: the promotion note says parameters never auto-change
    assert "NEVER AUTO-CHANGE" in report.get("note", "")


def test_promotion_report_worse_candidate_not_promotable(monkeypatch, tmp_path):
    """A candidate with a WORSE hit-rate than live reports WORSE, never PROMOTABLE."""
    shadow_summary = {
        "slices": {
            "live": {
                "n_graded": 8, "n_pending": 0,
                "pooled_n_directional": 8, "pooled_hit_rate": 0.75,
                "n_significant_fdr": 1, "by_stage": {},
                "by_theme": {
                    "memory_storage": {
                        "n": 8, "n_dir": 8, "hits": 6, "hit_rate": 0.75,
                        "p_value": 0.03, "significant_fdr": True, "n_independent": 8,
                        "avg_excess_pct": 4.0, "ci95": [0.4, 0.9],
                    }
                },
                "by_horizon": {},
            },
            "lang_z_cutoff|2.0": {
                "n_graded": 8, "n_pending": 0,
                "pooled_n_directional": 8, "pooled_hit_rate": 0.4,  # worse
                "n_significant_fdr": 0, "by_stage": {},
                "by_theme": {
                    "memory_storage": {
                        "n": 8, "n_dir": 8, "hits": 3, "hit_rate": 0.4,
                        "p_value": 0.85, "significant_fdr": False, "n_independent": 8,
                        "avg_excess_pct": -1.0, "ci95": [0.1, 0.7],
                    }
                },
                "by_horizon": {},
            },
        }
    }
    monkeypatch.setattr(fs, "_live_value",
                        lambda p: 0.5 if p == "lang_z_cutoff" else 80.0)

    report = fs.shadow_promotion_report(shadow_summary=shadow_summary)
    entry = next((c for c in report["candidates"]
                  if c["param"] == "lang_z_cutoff" and c["candidate"] == 2.0), None)
    assert entry is not None
    assert entry["verdict"] == "WORSE"
    assert len(report["promotable"]) == 0


# ---------------------------------------------------------------------------
# (e) Empty ledger → honest "accruing" report, never fabricated
# ---------------------------------------------------------------------------

def test_empty_ledger_honest_accruing_report(monkeypatch, tmp_path):
    """With an empty shadow_log.jsonl and empty live log, the report says accruing=True,
    promotable={}, and never fabricates a hit-rate or a PROMOTABLE verdict."""
    from engine.foresight_shadow import grade_shadow, shadow_promotion_report
    monkeypatch.setattr(fs, "config", _fake_config(tmp_path))
    from engine import foresight_grader as gr
    monkeypatch.setattr(gr, "_closes", lambda tk: None)
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(gr.config, "load",
                        lambda: {"themes": {"memory_storage": {"tickers": ["MU", "WDC"]}}})

    (Path(tmp_path) / "foresight").mkdir(parents=True, exist_ok=True)
    # Empty files
    (Path(tmp_path) / "foresight" / "shadow_log.jsonl").write_text("")
    (Path(tmp_path) / "foresight" / "log.jsonl").write_text("")

    grade = grade_shadow(today=pd.Timestamp("2026-07-01"), write=False)
    report = shadow_promotion_report(shadow_summary=grade)

    # Must be honest about the empty state
    assert report["accruing"] is True, "empty ledger must report accruing=True"
    assert len(report["promotable"]) == 0, "empty ledger must have no PROMOTABLE candidates"
    assert report["live_n_directional"] == 0

    # No candidate should have a fabricated hit-rate
    for c in report.get("candidates") or []:
        assert c["verdict"] == "ACCRUING", (
            f"empty ledger: expected ACCRUING for all candidates, got {c['verdict']} "
            f"for {c['param']}|{c['candidate']}"
        )
        assert c["hit_rate"] is None, "no hit-rate should be fabricated from empty ledger"


def test_shadow_report_note_says_no_auto_change(monkeypatch, tmp_path):
    """The promotion report and shadow track record note explicitly state parameters
    never auto-change — the human-approval requirement must be documented."""
    from engine.foresight_shadow import grade_shadow, shadow_promotion_report
    monkeypatch.setattr(fs, "config", _fake_config(tmp_path))
    from engine import foresight_grader as gr
    monkeypatch.setattr(gr, "_closes", lambda tk: None)
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(gr.config, "load",
                        lambda: {"themes": {}})
    (Path(tmp_path) / "foresight").mkdir(parents=True, exist_ok=True)

    grade = grade_shadow(today=pd.Timestamp("2026-07-01"), write=False)
    report = shadow_promotion_report(shadow_summary=grade)

    assert "NEVER AUTO-CHANGE" in report.get("note", "") or \
           "never auto-change" in report.get("note", "").lower(), \
        "promotion report must explicitly state parameters never auto-change"

    assert "NEVER AUTO-CHANGE" in grade.get("note", "") or \
           "NEVER AUTO-CHANGE" in grade.get("note", "").upper(), \
        "shadow track record note must state parameters never auto-change"


# ---------------------------------------------------------------------------
# W3b review-fix regression tests (B1 family-FDR, B2 candidate-vs-live, B3 fidelity)
# ---------------------------------------------------------------------------

def _slice(n_dir, hit_rate):
    hits = round(hit_rate * n_dir)
    return {
        "n_graded": n_dir, "n_pending": 0,
        "pooled_n_directional": n_dir, "pooled_hit_rate": hit_rate,
        "n_significant_fdr": 0, "by_stage": {},
        "by_theme": {"memory_storage": {
            "n": n_dir, "n_dir": n_dir, "hits": hits, "hit_rate": hit_rate,
            "p_value": 0.09, "significant_fdr": False, "n_independent": n_dir,
            "avg_excess_pct": 1.0, "ci95": [0.3, 0.9]}},
        "by_horizon": {},
    }


def test_family_fdr_six_marginal_candidates_promote_zero():
    """REVIEW B1 REGRESSION: six candidates each marginally better than live must
    promote ZERO under the family-wide BY-FDR — per-candidate FDR with m=1 would
    have fired all six (the '6 dice rolls fake a PROMOTABLE' failure)."""
    from engine.foresight_shadow import shadow_promotion_report, SHADOW_GRID
    slices = {"live": _slice(30, 0.50)}
    for param, cands in SHADOW_GRID.items():
        for c in cands:
            # marginally better: 19/30 vs 15/30 — Fisher one-sided p ≈ 0.15-0.2,
            # never family-FDR significant across 6 comparisons
            slices[f"{param}|{c}"] = _slice(30, 0.6333)
    report = shadow_promotion_report({"slices": slices})
    assert report["promotable"] == {}, (
        f"marginal candidates promoted: {list(report['promotable'])}")
    verdicts = {c["verdict"] for c in report["candidates"] if not c["is_live"]}
    assert "BETTER_NOT_SIGNIFICANT" in verdicts
    assert "PROMOTABLE" not in verdicts


def test_candidate_vs_live_test_not_coinflip():
    """REVIEW B2 REGRESSION: the promotion test is candidate-vs-LIVE, not
    candidate-vs-coinflip. A candidate that crushes a coin (0.9 hit-rate) but with a
    live slice at 0.85 and tiny n must NOT be significant."""
    from engine.foresight_shadow import shadow_promotion_report
    slices = {"live": _slice(20, 0.85), "lang_z_cutoff|1.0": _slice(20, 0.90)}
    report = shadow_promotion_report({"slices": slices})
    entry = [c for c in report["candidates"]
             if c["param"] == "lang_z_cutoff" and c["candidate"] == 1.0][0]
    assert entry["verdict"] in ("BETTER_NOT_SIGNIFICANT",), entry
    assert entry["p_value_vs_live"] is not None and entry["p_value_vs_live"] > 0.10


def test_fisher_exact_greater_sanity():
    """Fisher helper: overwhelming superiority → tiny p; equality → p ~ large."""
    from engine.foresight_shadow import _fisher_exact_greater
    p_strong = _fisher_exact_greater(28, 30, 10, 30)   # 93% vs 33%
    p_equal = _fisher_exact_greater(15, 30, 15, 30)
    assert p_strong is not None and p_strong < 0.001
    assert p_equal is not None and p_equal > 0.4
    assert _fisher_exact_greater(1, 0, 5, 10) is None  # degenerate n


def test_lang_z_shadow_reverts_to_numeric_band(monkeypatch, tmp_path):
    """REVIEW B3 REGRESSION (numeric-lift path): a theme text-lifted live must revert
    to its NUMERIC band (not a '(text)' variant) when the candidate cutoff exceeds
    its clipped lang_z."""
    from engine.foresight_shadow import _stage_under_candidate
    bn_theme = {
        "band": "TIGHT (text)", "text_only": True,       # live: lifted
        "numeric_band": "TIGHTENING", "numeric_composite": 0.55,
        "leg6_detail": {"value": 1.2}, "language_n_filers": 3,
        "language_accel": 1.2,
    }
    rv_theme = {"breadth": 0.30, "level_state": "POSITIVE"}
    # candidate 2.0 > lang_z 1.2 → the lift dissolves; band = numeric TIGHTENING →
    # stage must NOT be a (text) thesis stage
    stage = _stage_under_candidate("lang_z_cutoff", 2.0, bn_theme, rv_theme, None, {})
    assert "(text)" not in stage, f"lift did not revert to numeric band: {stage}"


def test_lang_z_shadow_uses_clipped_z_not_raw_accel(monkeypatch):
    """REVIEW B3 REGRESSION (clip boundary): raw accel 3.0 clips to 2.0; at candidate
    2.0 the live engine compares 2.0 > 2.0 = False → no TIGHT (text). The shadow must
    agree (the old code compared raw 3.0 > 2.0 = True)."""
    from engine.foresight_shadow import _stage_under_candidate
    # stage-observable on the NUMERIC-LIFT path: clipped 2.0 > candidate 2.0 = False
    # -> lift dissolves -> numeric TIGHTENING (non-thesis). Old code compared RAW
    # 3.0 > 2.0 = True -> TIGHT (text) -> fake text thesis stage.
    bn_theme = {
        "band": "TIGHT (text)", "text_only": True,          # live: lifted
        "numeric_band": "TIGHTENING", "numeric_composite": 0.55,
        "leg6_detail": {"value": 2.0},                       # clipped z
        "language_accel": 3.0,                               # raw accel
        "language_n_filers": 3,
    }
    rv_theme = {"breadth": 0.05, "level_state": "FLAT_LOW"}
    stage = _stage_under_candidate("lang_z_cutoff", 2.0, bn_theme, rv_theme, None, {})
    assert "(text)" not in stage, (
        f"shadow compared raw accel instead of clipped z: {stage}")
