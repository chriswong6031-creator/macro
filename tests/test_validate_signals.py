"""Tests for the signal→chart contract gate (scripts/validate_signals.py + SCHEMA.json).

A valid fixture passes clean; each invalid fixture (missing ticker, quality on a 'sell',
non-date 'date', unsorted markers, plus the brain-leaf shape) must produce at least one
error. The real SCHEMA.json is loaded — these tests double as a guard that the schema and
the validator agree on the §7 contract.
"""
from __future__ import annotations

import json

from scripts import validate_signals as vs


SCHEMA = vs.load_schema()


# ---- valid fixtures -------------------------------------------------------

def _valid_ticker() -> dict:
    return {
        "ticker": "AAPL", "asof": "2026-06-18", "tf": "3D",
        "state": "long-bias", "above200": True, "weekly_bull": False,
        "trail_stop": 187.42, "trail_breach": False,
        "risk_flags": ["2025-08-20", "2026-02-04"],
        "early_markers": ["2025-07-09", "2026-03-05"], "early_now": False,
        "markers": [
            {"date": "2025-07-16", "type": "buy", "quality": "take", "reason": "held confirmation"},
            {"date": "2025-09-30", "type": "sell"},
            {"date": "2026-01-16", "type": "cut"},
            {"date": "2026-03-12", "type": "rebuy", "quality": "block", "reason": "counter-trend, no reclaim"},
            {"date": "2026-06-16", "type": "buy", "quality": "pending", "reason": "pending confirmation"},
        ],
    }


def _valid_leaf() -> dict:
    return {
        "asof": "2026-06-16", "tf": "3D", "universe": "us_deep",
        "note": "entry-quality RISK signal (display-only, NOT alpha)",
        "signals": [
            {"ticker": "AAPL", "asof": "2026-06-18", "state": "short-bias",
             "above200": True, "weekly_bull": True, "trail_stop": 187.42, "trail_breach": False,
             "early_now": False, "last": {"date": "2026-06-10", "type": "sell"}},
            {"ticker": "BA", "asof": "2026-06-16", "state": "long-bias",
             "above200": True, "weekly_bull": False, "trail_stop": None, "trail_breach": False,
             "early_now": True,
             "last": {"date": "2026-06-16", "type": "buy", "quality": "pending", "reason": "pending confirmation"}},
            {"ticker": "XYZ", "asof": "2026-06-16", "state": "mixed",
             "above200": False, "weekly_bull": False, "trail_stop": 12.5, "trail_breach": True,
             "early_now": False, "last": None},
        ],
    }


def test_valid_ticker_passes():
    assert vs.validate_ticker_doc(_valid_ticker(), SCHEMA, "fix") == []


def test_valid_leaf_passes():
    assert vs.validate_brain_leaf(_valid_leaf(), SCHEMA, "fix") == []


def test_pending_quality_is_accepted():
    # `pending` is a real third quality value the engine emits — the schema MUST allow it.
    doc = _valid_ticker()
    doc["markers"] = [{"date": "2026-06-16", "type": "buy", "quality": "pending", "reason": "x"}]
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix") == []


def test_pit_disclosure_is_accepted():
    # RC-R2 (engine/marker_integrity.py) appends a `pit` drift-disclosure dict to
    # every per-ticker file. The 2026-07-12 nightlies failed the §7 gate wholesale
    # (226/226 files) because the schema lagged the writer — pit MUST validate.
    doc = _valid_ticker()
    doc["pit"] = {
        "kept_frozen": 3906, "refined": 0, "appended": 0, "drift_lost": 0,
        "drift_deep_new": 0, "relabel_blocked": 0, "prev_asof": "2026-07-09",
        "last_night": {"kept_frozen": 279, "refined": 0, "appended": 0,
                       "drift_lost": 0, "drift_deep_new": 0, "relabel_blocked": 0},
    }
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix") == []


def test_pit_first_write_null_prev_asof_accepted():
    # First-ever write has no prior vintage: merge_payload sets prev_asof=None.
    doc = _valid_ticker()
    doc["pit"] = {"kept_frozen": 0, "prev_asof": None, "last_night": {}}
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix") == []


def test_engine_analyze_output_conforms_to_schema():
    """The live engine's analyze() output MUST validate against the schema.

    This is the key anti-drift test: a change to engine/signal_quality.py that adds, renames, or
    re-types a field without updating SCHEMA.json would make additionalProperties:false reject the
    output here — failing the test BEFORE it can ship. Uses a deterministic synthetic series (no
    RNG) so it is stable across runs and needs no data fixtures.
    """
    import numpy as np
    import pandas as pd
    from engine.signal_quality import analyze

    idx = pd.bdate_range("2019-01-01", periods=900)
    t = np.arange(len(idx), dtype=float)
    close = pd.Series(100 + 18 * np.sin(t / 33) + 0.015 * t + 4 * np.sin(t / 6), index=idx)
    res = analyze("SYNTH", close)
    assert res is not None, "engine produced no result for a 900-bar series"
    assert vs.validate_ticker_doc(res, SCHEMA, "engine analyze()") == []
    # The brain-leaf entry derived from analyze() (per §7.B) must also conform.
    entry = {k: res[k] for k in ("ticker", "asof", "state", "above200", "weekly_bull",
                                 "trail_breach", "trail_stop", "early_now")}
    entry["last"] = res["markers"][-1] if res["markers"] else None
    leaf = {"asof": res["asof"], "tf": "3D", "universe": "us_deep", "signals": [entry]}
    assert vs.validate_brain_leaf(leaf, SCHEMA, "engine leaf") == []


# ---- invalid fixtures (each must fail) ------------------------------------

def test_missing_ticker_fails():
    doc = _valid_ticker()
    del doc["ticker"]
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix")


def test_quality_on_sell_fails():
    doc = _valid_ticker()
    doc["markers"] = [{"date": "2025-09-30", "type": "sell", "quality": "take"}]
    errs = vs.validate_ticker_doc(doc, SCHEMA, "fix")
    assert errs
    assert any("quality" in e for e in errs)


def test_quality_on_cut_fails():
    doc = _valid_ticker()
    doc["markers"] = [{"date": "2026-01-16", "type": "cut", "quality": "block"}]
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix")


def test_non_date_date_fails():
    doc = _valid_ticker()
    doc["markers"] = [{"date": "07/16/2025", "type": "buy", "quality": "take", "reason": "x"}]
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix")


def test_bad_calendar_date_fails():
    # passes the YYYY-MM-DD pattern but is not a real date — must still be rejected.
    doc = _valid_ticker()
    doc["markers"] = [{"date": "2026-13-45", "type": "buy", "quality": "take", "reason": "x"}]
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix")


def test_unsorted_markers_fail():
    doc = _valid_ticker()
    doc["markers"] = [
        {"date": "2026-03-12", "type": "sell"},
        {"date": "2025-07-16", "type": "buy", "quality": "take", "reason": "x"},
    ]
    errs = vs.validate_ticker_doc(doc, SCHEMA, "fix")
    assert errs
    assert any("ascending" in e or "after" in e for e in errs)


def test_duplicate_date_markers_fail():
    # strict ascending — two markers on the same bar date is a contract violation.
    doc = _valid_ticker()
    doc["markers"] = [
        {"date": "2025-07-16", "type": "buy", "quality": "take", "reason": "x"},
        {"date": "2025-07-16", "type": "sell"},
    ]
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix")


def test_bad_state_fails():
    doc = _valid_ticker()
    doc["state"] = "bullish"  # not in [long-bias, short-bias, mixed]
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix")


def test_unknown_marker_type_fails():
    doc = _valid_ticker()
    doc["markers"] = [{"date": "2025-07-16", "type": "scale-in"}]
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix")


def test_extra_field_fails():
    # additionalProperties:false — a stray/typo'd field is exactly the drift we want to catch.
    doc = _valid_ticker()
    doc["confidence"] = 0.9
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix")


def test_leaf_missing_signals_fails():
    leaf = _valid_leaf()
    del leaf["signals"]
    assert vs.validate_brain_leaf(leaf, SCHEMA, "fix")


def test_leaf_quality_on_sell_last_fails():
    leaf = _valid_leaf()
    leaf["signals"][0]["last"] = {"date": "2026-06-10", "type": "sell", "quality": "take"}
    errs = vs.validate_brain_leaf(leaf, SCHEMA, "fix")
    assert errs
    assert any("quality" in e for e in errs)


# ---- new rules: trail layer + cross-shape consistency ---------------------

def test_buy_without_quality_fails():
    # the chart needs quality on every buy/rebuy — a bare buy is a drift the gate must catch.
    doc = _valid_ticker()
    doc["markers"] = [{"date": "2025-07-16", "type": "buy"}]
    errs = vs.validate_ticker_doc(doc, SCHEMA, "fix")
    assert errs
    assert any("quality" in e and "missing" in e for e in errs)


def test_rebuy_without_quality_fails():
    doc = _valid_ticker()
    doc["markers"] = [{"date": "2025-07-16", "type": "rebuy"}]
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix")


def test_reason_on_sell_fails():
    doc = _valid_ticker()
    doc["markers"] = [{"date": "2025-09-30", "type": "sell", "reason": "should not be here"}]
    errs = vs.validate_ticker_doc(doc, SCHEMA, "fix")
    assert errs
    assert any("reason" in e for e in errs)


def test_trail_fields_valid_passes():
    # trail_stop/trail_breach/risk_flags are the display-only risk layer — accepted when well-formed.
    assert vs.validate_ticker_doc(_valid_ticker(), SCHEMA, "fix") == []


def test_trail_stop_null_passes():
    doc = _valid_ticker()
    doc["trail_stop"] = None  # null when insufficient history
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix") == []


def test_risk_flags_unsorted_fails():
    doc = _valid_ticker()
    doc["risk_flags"] = ["2026-02-04", "2025-08-20"]  # descending
    errs = vs.validate_ticker_doc(doc, SCHEMA, "fix")
    assert errs
    assert any("risk_flags" in e and "ascending" in e for e in errs)


def test_risk_flags_bad_date_fails():
    doc = _valid_ticker()
    doc["risk_flags"] = ["2025-08-20", "not-a-date"]
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix")


def test_risk_flag_in_markers_stream_fails():
    # risk_flag must NOT leak into the trade-marker stream (it has its own list).
    doc = _valid_ticker()
    doc["markers"] = [{"date": "2025-07-16", "type": "risk_flag"}]
    assert vs.validate_ticker_doc(doc, SCHEMA, "fix")


def test_early_markers_unsorted_fails():
    # early_markers is the 2D-MACD advance-warning date list — also must be ascending.
    doc = _valid_ticker()
    doc["early_markers"] = ["2026-03-05", "2025-07-09"]  # descending
    errs = vs.validate_ticker_doc(doc, SCHEMA, "fix")
    assert errs
    assert any("early_markers" in e and "ascending" in e for e in errs)


# ---- end-to-end run() over a temp tree ------------------------------------

def _write_tree(tmp_path, leaf):
    """Write one per-ticker file for every leaf ticker so the leaf ⊆ files invariant holds."""
    sigdir = tmp_path / "signals"
    sigdir.mkdir()
    for s in leaf["signals"]:
        doc = _valid_ticker()
        doc["ticker"] = s["ticker"]
        (sigdir / f"{s['ticker']}.json").write_text(json.dumps(doc))
    leaf_path = tmp_path / "leaf.json"
    leaf_path.write_text(json.dumps(leaf))
    return sigdir, leaf_path


def test_run_passes_on_valid_tree(tmp_path):
    leaf = _valid_leaf()
    sigdir, leaf_path = _write_tree(tmp_path, leaf)
    audit = tmp_path / "audit.json"
    rc = vs.run(signals_dir=sigdir, leaf_path=leaf_path, audit_path=audit)
    assert rc == 0
    a = json.loads(audit.read_text())
    assert a["errors"] == []
    assert a["files_checked"] == len(leaf["signals"]) + 1
    assert a["n_markers"] == len(leaf["signals"]) * len(_valid_ticker()["markers"])
    assert a["asof"] == "2026-06-16"


def test_run_fails_and_writes_audit_on_invalid_tree(tmp_path):
    leaf = _valid_leaf()
    sigdir, leaf_path = _write_tree(tmp_path, leaf)
    bad = _valid_ticker()
    bad["ticker"] = "AAPL"
    del bad["ticker"]  # corrupt the AAPL file (missing required field)
    (sigdir / "AAPL.json").write_text(json.dumps(bad))
    audit = tmp_path / "audit.json"
    rc = vs.run(signals_dir=sigdir, leaf_path=leaf_path, audit_path=audit)
    assert rc == 1
    assert json.loads(audit.read_text())["errors"]


def test_run_fails_on_leaf_missing_per_ticker_file(tmp_path):
    # leaf lists a ticker with no per-ticker file -> partial/inconsistent write.
    leaf = _valid_leaf()
    sigdir, leaf_path = _write_tree(tmp_path, leaf)
    (sigdir / "BA.json").unlink()  # drop a file the leaf still claims
    audit = tmp_path / "audit.json"
    rc = vs.run(signals_dir=sigdir, leaf_path=leaf_path, audit_path=audit)
    assert rc == 1
    assert any("BA" in e and "missing" in e for e in json.loads(audit.read_text())["errors"])


def test_run_fails_when_leaf_missing(tmp_path):
    sigdir = tmp_path / "signals"
    sigdir.mkdir()
    (sigdir / "AAPL.json").write_text(json.dumps(_valid_ticker()))
    audit = tmp_path / "audit.json"
    rc = vs.run(signals_dir=sigdir, leaf_path=tmp_path / "nope.json", audit_path=audit)
    assert rc == 1
