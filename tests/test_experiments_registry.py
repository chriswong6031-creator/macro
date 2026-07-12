"""tests/test_experiments_registry.py — compute() must normalize BOTH seed keysets.

Newer entries in data/experiments/registry_seed.json (hazard-live-reliability-*,
w5a-reversal-rederive, hkca-*, w3*-…) were authored with title/hypothesis/registered_on
instead of name/what/started. compute() must fall back across the alternate keyset so
the emitted site/marketdata/experiments.json never carries name=null / what=null — the
admin Experiments tab (admin/static/app.js) renders those fields directly.
"""
from __future__ import annotations

from engine import experiments_registry


def _compute_with_seed(monkeypatch, entries: list[dict]) -> list[dict]:
    """Run compute() against a synthetic seed; all other reads (hooks) return None."""
    seed = {"experiments": entries}
    monkeypatch.setattr(
        experiments_registry, "_read_json",
        lambda rel: seed if rel == experiments_registry.SEED else None)
    return experiments_registry.compute()["experiments"]


def test_every_real_seed_entry_emits_name_and_what():
    """Regression: every entry in the real seed must produce non-null name AND what."""
    payload = experiments_registry.compute()
    assert payload["n"] > 0
    no_name = [r["id"] for r in payload["experiments"] if not r.get("name")]
    no_what = [r["id"] for r in payload["experiments"] if not r.get("what")]
    assert not no_name, f"seed entries emitted with name=null: {no_name}"
    assert not no_what, f"seed entries emitted with what=null: {no_what}"


def test_alternate_keyset_normalized(monkeypatch):
    rec = _compute_with_seed(monkeypatch, [{
        "id": "alt-1", "title": "Alt title", "kind": "phase0_backtest",
        "hypothesis": "Alt hypothesis", "status": "accruing",
        "program": "hk_canada_stocks", "wave": "W3", "channel": "C5", "phase": "phase-0",
        "registered_on": "2026-07-03", "come_back_on": "2099-01-15",
        "come_back_note": "note", "pr": "w3(c5-collector-fix)",
        "verdict": "NO-GO", "result": "x" * 600,
    }])[0]
    assert rec["name"] == "Alt title"
    assert rec["what"] == "Alt hypothesis"
    assert rec["started"] == "2026-07-03"
    assert rec["source"] == "w3(c5-collector-fix)"
    assert rec["phase_hint"] == "hk_canada_stocks · W3 · C5 · phase-0"
    assert rec["state"].startswith("verdict=NO-GO")
    assert len(rec["state"]) <= 400  # paragraph-length verdicts/results are capped


def test_alternate_keyset_skips_na_segments(monkeypatch):
    rec = _compute_with_seed(monkeypatch, [{
        "id": "alt-2", "title": "T", "hypothesis": "H",
        "program": "hk_canada_stocks", "wave": "N/A", "channel": "C2", "phase": "ACCRUE",
    }])[0]
    assert rec["phase_hint"] == "hk_canada_stocks · C2 · ACCRUE"
    assert rec["state"] is None  # no verdict/result → no fabricated state


def test_track_record_hook_ready_only_on_graded_verdict(monkeypatch):
    """Fix 2026-07-12: verdict='measuring' (rows matured, significance gate not yet
    callable — subsector_track_record vocabulary) must NOT flag ready; it lit
    subsector-rotation 'ready' 44 days before its callable-verdict date. A graded
    verdict (validated / a printed null) still must flag ready — nulls are printed."""
    monkeypatch.setattr(experiments_registry, "_jsonl_dates", lambda rel: (11, 2948))
    for verdict, expect in [("accruing", None), ("measuring", None),
                            ("validated", True), ("null", True)]:
        monkeypatch.setattr(
            experiments_registry, "_read_json",
            lambda rel, v=verdict: {"verdict": v, "horizons": {}})
        out = experiments_registry._refresh_track_record(
            {"storage": "data/x/snapshots.jsonl", "track_json": "data/x/track_record.json"})
        assert out.get("ready") is expect, (verdict, out)


def test_canonical_keyset_takes_precedence(monkeypatch):
    rec = _compute_with_seed(monkeypatch, [{
        "id": "canon-1", "name": "Canon name", "what": "Canon what",
        "started": "2026-06-30", "source": "engine/x.py",
        "phase_hint": "existing hint", "state": "existing state",
        # alternate keys present too — must NOT override the canonical values
        "title": "loser", "hypothesis": "loser", "registered_on": "1999-01-01",
        "pr": "loser", "program": "loser", "verdict": "loser",
    }])[0]
    assert rec["name"] == "Canon name"
    assert rec["what"] == "Canon what"
    assert rec["started"] == "2026-06-30"
    assert rec["source"] == "engine/x.py"
    assert rec["phase_hint"] == "existing hint"
    assert rec["state"] == "existing state"
