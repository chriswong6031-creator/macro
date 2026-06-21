"""Calibration Hub (engine/calibration_hub.py) — the unified observability surface.

Verifies the per-desk health classification (cold / weak / inverted / calibrated), the
conviction-monotonicity read, the Trial Ledger roll-up, and that build/render degrade
gracefully on missing inputs.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import calibration_hub as ch  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402


def _new_root():
    return Path(tempfile.mkdtemp())


def _write_track(root, slug, track):
    d = root / "data" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "track_record.json").write_text(json.dumps(track))


def _bucket(n, hits):
    return {"n": n, "hits": hits, "misses": n - hits,
            "hit_rate": round(hits / n, 3) if n else None}


def test_cold_desk_when_sample_small():
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 3, "open": 5, "overall": _bucket(3, 2)})
    s = ch.build(root)
    ai = next(d for d in s["desks"] if d["slug"] == "ai_desk")
    assert ai["health"] == "cold" and ai["scored"] == 3


def test_weak_desk_below_coinflip():
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 20, "open": 0,
                                   "overall": _bucket(20, 7),  # 35% hit
                                   "by_conviction": {"high": _bucket(8, 3), "low": _bucket(8, 3)}})
    s = ch.build(root)
    ai = next(d for d in s["desks"] if d["slug"] == "ai_desk")
    assert ai["health"] == "weak"


def test_inverted_conviction_flagged():
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 20, "open": 0,
                                   "overall": _bucket(20, 12),
                                   # high hits LESS than low → conviction means nothing
                                   "by_conviction": {"high": _bucket(10, 4), "low": _bucket(10, 8)}})
    s = ch.build(root)
    ai = next(d for d in s["desks"] if d["slug"] == "ai_desk")
    assert ai["health"] == "inverted"
    assert ai["conviction_monotone"] is False


def test_calibrated_desk():
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 20, "open": 0,
                                   "overall": _bucket(20, 13),
                                   "by_conviction": {"high": _bucket(10, 8), "low": _bucket(10, 5)},
                                   "by_regime": {"Goldilocks": _bucket(12, 8)}})
    s = ch.build(root)
    ai = next(d for d in s["desks"] if d["slug"] == "ai_desk")
    assert ai["health"] == "calibrated"
    assert ai["conviction_monotone"] is True
    assert ai["regimes"] == ["Goldilocks"]


def test_loops_live_vs_cold_count():
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 20, "overall": _bucket(20, 13),
                                   "by_conviction": {"high": _bucket(10, 8), "low": _bucket(10, 5)}})
    _write_track(root, "radar", {"scored_total": 2, "overall": _bucket(2, 1)})  # cold
    s = ch.build(root)
    assert s["loops"]["live"] == 1            # ai_desk
    assert s["loops"]["cold"] == len(s["desks"]) - 1   # radar + the 4 absent desks


def test_trial_ledger_rollup():
    root = _new_root()
    led = TrialLedger(root / "data" / "trial_ledger.jsonl", family="vector")
    led.log_grid([{"v": i} for i in range(4)])
    led.log_declared_budget(65)
    led.log_declared_budget(8, family="tactical")
    s = ch.build(root)
    tl = {f["family"]: f for f in s["trial_ledger"]["families"]}
    assert tl["vector"]["effective_n"] == 65 and tl["vector"]["itemized"] == 4
    assert tl["tactical"]["effective_n"] == 8
    assert s["trial_ledger"]["total_families"] == 2


def test_run_persists_json_and_html():
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 20, "overall": _bucket(20, 13),
                                   "by_conviction": {"high": _bucket(10, 8), "low": _bucket(10, 5)}})
    s = ch.run(root=root, persist=True)
    assert (root / "data" / "calibration" / "summary.json").exists()
    html = (root / "site" / "calibration.html").read_text()
    assert "Calibration Hub" in html and "AI Desk" in html
    assert ch.render_markdown(s).startswith("# Calibration Hub")


def test_build_degrades_with_no_inputs():
    root = _new_root()
    s = ch.build(root)                          # nothing present
    assert s["loops"]["live"] == 0
    assert all(d["health"] == "cold" for d in s["desks"])
    assert s["trial_ledger"]["families"] == []
