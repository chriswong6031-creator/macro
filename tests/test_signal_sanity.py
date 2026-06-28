"""Signal-sanity tripwire — each invariant must TRIP on a synthetic break and PASS when healthy.

Run:  /Users/chriswong/Documents/Cluade/Macro Dashboard/.venv/bin/python -m pytest tests/test_signal_sanity.py -q
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from engine import signal_sanity as ss  # noqa: E402
from scripts import signal_sanity as runner  # noqa: E402

NOW = datetime(2026, 6, 21, 22, 0, 0)
ASOF = "2026-06-21"


# ---------------------------------------------------------------------------
# synthetic healthy boards (varied scores, full coverage)
# ---------------------------------------------------------------------------

def _standouts(n=120, as_of=ASOF):
    return {"as_of": as_of, "buy": [
        {"ticker": f"S{i}", "alpha": round((i % 53) / 10.0, 3),
         "conviction": {"score": 100 - (i % 15), "composite_z": round(1.2 - i * 0.006, 4)}}
        for i in range(n)]}


def _briefing(n=25, as_of=ASOF):
    return {"as_of": as_of,
            "priority_queue": [{"ticker": f"B{i}", "priority": round(0.95 - i * 0.02, 3),
                                "strength": round(0.9 - i * 0.015, 3)} for i in range(n)],
            "divergences": [{"ticker": f"D{i}", "lean": 1} for i in range(20)]}  # lean≡1 by design


def _radar(n=170, as_of=ASOF):
    ts = []
    for i in range(n):
        state = "QUIET" if i % 5 == 0 else ("CONFIRMED_UP" if i % 2 else "POSITIVE_DIVERGENCE")
        ts.append({"ticker": f"R{i}", "state": state,
                   "edge_score": None if state == "QUIET" else (i % 97)})
    return {"as_of": as_of, "tickers": ts}


def _altdata(n=30, as_of=ASOF):
    return {"as_of": as_of, "signals": [
        {"ticker": f"A{i}", "signal_score": 40 + (i % 57), "weighted_score": round(0.9 + i * 0.05, 3)}
        for i in range(n)]}


def _news(n_with=200, n_zero=120, as_of=ASOF):
    tk = {f"N{i}": {"n_recent": 1 + (i % 6), "sentiment_score": round((i % 5) / 2.0 - 1, 2)}
          for i in range(n_with)}
    tk.update({f"Z{i}": {"n_recent": 0, "sentiment_score": 0} for i in range(n_zero)})
    return {"asof": as_of, "tickers": tk}   # NB: 'asof', no underscore


def _hub(n=30, as_of=ASOF):
    return {"as_of": as_of, "command": [
        {"ticker": f"H{i}", "composite_conviction": round(100 - i * 1.5, 1),
         "opportunity_score": round(90 - i * 1.2, 1), "edge_remaining": round(0.9 - i * 0.01, 3),
         "falsifier_penalty": 1}  # falsifier_penalty≡1 by design — must NOT be flagged
        for i in range(n)]}


def healthy():
    return {"standouts": _standouts(), "briefing": _briefing(), "radar": _radar(),
            "altdata": _altdata(), "news": _news(), "intel_hub": _hub()}


# ---------------------------------------------------------------------------
# healthy → clean
# ---------------------------------------------------------------------------

def test_healthy_passes_clean():
    rep = ss.evaluate_all(healthy(), None, now=NOW, cfg={})
    assert rep["ok"] is True, rep["fail_reasons"]
    assert rep["fail_reasons"] == []
    assert rep["warnings"] == []          # by-design constants (divergences.lean, falsifier_penalty) NOT flagged
    assert set(rep["checked"]) == {s.key for s in ss.SURFACES}


# ---------------------------------------------------------------------------
# 1. COVERAGE — the top_n=16 class
# ---------------------------------------------------------------------------

def test_coverage_collapse_fails():
    p = healthy()
    p["standouts"] = _standouts(n=16)          # 800→16-style cut
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})
    assert rep["ok"] is False
    assert any("standouts: coverage 16 < floor 40" in f for f in rep["fail_reasons"])


def test_news_coverage_keys_on_names_with_stories():
    p = healthy()
    p["news"] = _news(n_with=50, n_zero=500)   # 550 keys but only 50 carry news < floor 100
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})
    assert rep["ok"] is False
    assert any("news: coverage 50 < floor 100" in f for f in rep["fail_reasons"])


# ---------------------------------------------------------------------------
# 2. DEGENERACY — the dead-lens class
# ---------------------------------------------------------------------------

def test_constant_score_column_fails():
    p = healthy()
    for r in p["standouts"]["buy"]:
        r["conviction"]["composite_z"] = 1.0   # column went constant
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})
    assert rep["ok"] is False
    assert any("standouts.conviction.composite_z" in f and "zero-variance" in f for f in rep["fail_reasons"])


def test_all_null_score_column_fails():
    p = healthy()
    for r in p["radar"]["tickers"]:
        if r["state"] != "QUIET":
            r["edge_score"] = None              # the consumed signal went all-null
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})
    assert rep["ok"] is False
    assert any("radar.edge_score" in f and "null" in f for f in rep["fail_reasons"])


def test_by_design_constants_not_flagged():
    # hub falsifier_penalty≡1 and briefing divergences.lean≡1 are healthy; only the chosen
    # varying columns are judged. A fully healthy board must stay clean.
    rep = ss.evaluate_all(healthy(), None, now=NOW, cfg={})
    assert not any("falsifier_penalty" in f for f in rep["fail_reasons"] + rep["warnings"])
    assert not any("lean" in f for f in rep["fail_reasons"] + rep["warnings"])


# ---------------------------------------------------------------------------
# 3. CONTENT-FREEZE — as_of advanced but values identical
# ---------------------------------------------------------------------------

def test_content_freeze_fails():
    p = healthy()
    rows = ss.baseline_rows(ss.evaluate_all(p, None, now=NOW, cfg={}))
    fp = next(r["fingerprint"] for r in rows if r["surface"] == "standouts")
    prior = {"standouts": {"as_of": "2026-06-20", "fingerprint": fp, "scores": {}}}  # prior vintage, same values
    rep = ss.evaluate_all(p, prior, now=NOW, cfg={})   # same payload, as_of still 2026-06-21
    assert rep["ok"] is False
    assert any("standouts" in f and "FROZEN" in f for f in rep["fail_reasons"])


def test_same_vintage_rerun_does_not_flag_freeze():
    p = healthy()
    rows = ss.baseline_rows(ss.evaluate_all(p, None, now=NOW, cfg={}))
    fp = next(r["fingerprint"] for r in rows if r["surface"] == "standouts")
    prior = {"standouts": {"as_of": ASOF, "fingerprint": fp, "scores": {}}}  # SAME as_of → same-day rerun
    rep = ss.evaluate_all(p, prior, now=NOW, cfg={})
    assert not any("FROZEN" in f for f in rep["fail_reasons"])


# ---------------------------------------------------------------------------
# 4. STALENESS (warn) + 5. DRIFT (warn)
# ---------------------------------------------------------------------------

def test_relative_staleness_warns():
    p = healthy()
    p["altdata"] = _altdata(as_of="2026-06-18")        # a non-exempt board 3d behind (rel_stale_days=2)
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})
    assert rep["ok"] is True                            # warning, not a hard fail
    assert any("altdata" in w and "lags the freshest board" in w for w in rep["warnings"])


def test_standouts_exempt_from_relative_staleness():
    # standouts stamps the last-trading-day, so a 3d lag vs siblings is the NORMAL weekend state —
    # it must not relative-warn (its absolute staleness check still catches a genuine freeze).
    p = healthy()
    p["standouts"] = _standouts(as_of="2026-06-18")
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})
    assert not any("standouts" in w and "lags the freshest board" in w for w in rep["warnings"])


def test_distribution_drift_warns():
    p = healthy()
    prior = {"briefing": {"as_of": "2026-06-20", "fingerprint": "deadbeef",
                          "scores": {"priority": {"mean": 0.1}}}}   # today's mean ~0.7 → big drift
    rep = ss.evaluate_all(p, prior, now=NOW, cfg={})
    assert any("briefing.priority" in w and "drifted" in w for w in rep["warnings"])


# ---------------------------------------------------------------------------
# missing boards
# ---------------------------------------------------------------------------

def test_missing_required_board_fails():
    p = healthy()
    p["altdata"] = None
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})
    assert rep["ok"] is False
    assert "altdata" in rep["missing"]
    assert any("altdata: board missing" in f for f in rep["fail_reasons"])


def test_missing_board_optional_when_require_all_false():
    p = healthy()
    p["altdata"] = None
    rep = ss.evaluate_all(p, None, now=NOW, cfg={"require_all": False})
    assert rep["ok"] is True
    assert any("altdata: board absent" in w for w in rep["warnings"])


def test_malformed_board_degrades_not_raises():
    p = healthy()
    p["briefing"] = {"as_of": ASOF, "priority_queue": "not-a-list"}   # wrong type
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})   # must not raise
    assert rep["ok"] is False                          # empty/garbage container → coverage fail


def test_infinite_score_degrades_not_raises():
    # a divide-by-zero builder emits Infinity into a score column; statistics.pstdev would raise on
    # inf — _num must drop it so the check degrades (the contract) instead of crashing the whole run.
    p = healthy()
    for r in p["altdata"]["signals"]:
        r["signal_score"] = float("inf")
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})    # must not raise
    # inf dropped → signal_score reads as all-null over the populated set → degeneracy fail (caught, not crashed)
    assert rep["ok"] is False
    assert any("altdata.signal_score" in f for f in rep["fail_reasons"])


def test_nan_and_inf_excluded_by_num():
    assert ss._num(float("inf")) is None
    assert ss._num(float("-inf")) is None
    assert ss._num(float("nan")) is None
    assert ss._num(True) is None
    assert ss._num(3) == 3.0


def test_malformed_floors_config_degrades_not_raises():
    rep = ss.evaluate_all(healthy(), None, now=NOW, cfg={"floors": [40, 8]})   # list, not a dict
    assert isinstance(rep["ok"], bool)                 # must not raise; falls back to spec floors
    assert rep["ok"] is True


# ---------------------------------------------------------------------------
# false-positive fixes (news degeneracy exemptions, radar small-subset)
# ---------------------------------------------------------------------------

def test_news_uniform_sentiment_does_not_fail():
    # Polygon-insights outage: every news-bearing name → sentiment_score 0.0 while RSS headlines
    # flow. That is a context-only column going flat, NOT a broken news board → must not hard-fail.
    p = healthy()
    for v in p["news"]["tickers"].values():
        if v.get("n_recent", 0) >= 1:
            v["sentiment_score"] = 0.0
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})
    assert rep["ok"] is True
    assert not any("sentiment_score" in f for f in rep["fail_reasons"])


def test_news_uniform_n_recent_does_not_fail():
    # a quiet day where every covered name has exactly one story is a valid low-news state.
    p = healthy()
    for v in p["news"]["tickers"].values():
        if v.get("n_recent", 0) >= 1:
            v["n_recent"] = 1
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})
    assert rep["ok"] is True
    assert not any("n_recent" in f for f in rep["fail_reasons"])


def test_radar_small_constant_subset_warns_not_fails():
    # a low-divergence day: few non-QUIET names sharing one coarse integer edge_score must WARN
    # (subset below the radar min_pop=20 bar), not hard-fail the zero-variance check.
    p = healthy()
    ts = [{"ticker": f"R{i}", "state": "QUIET", "edge_score": None} for i in range(160)]
    ts += [{"ticker": f"U{i}", "state": "CONFIRMED_UP", "edge_score": 5} for i in range(10)]  # 10 < 20
    p["radar"] = {"as_of": ASOF, "tickers": ts}
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})
    assert rep["ok"] is True                                       # not a hard fail
    assert any("radar.edge_score" in w and "subset only 10" in w for w in rep["warnings"])


def test_radar_large_constant_subset_still_fails():
    # but a genuinely degenerate radar (many non-QUIET names all on one value) is still a hard fail.
    p = healthy()
    ts = [{"ticker": f"U{i}", "state": "CONFIRMED_UP", "edge_score": 5} for i in range(60)]
    p["radar"] = {"as_of": ASOF, "tickers": ts}
    rep = ss.evaluate_all(p, None, now=NOW, cfg={})
    assert rep["ok"] is False
    assert any("radar.edge_score" in f and "identical" in f for f in rep["fail_reasons"])


def test_fingerprint_order_independent_with_duplicate_tickers():
    s = ss._BY_KEY["standouts"]
    a = [{"ticker": "AAA", "conviction": {"composite_z": 1.0}, "alpha": 0.1},
         {"ticker": "AAA", "conviction": {"composite_z": 2.0}, "alpha": 0.2}]
    assert ss._fingerprint(s, a) == ss._fingerprint(s, list(reversed(a)))   # order must not change the hash


# ---------------------------------------------------------------------------
# config overrides
# ---------------------------------------------------------------------------

def test_floor_override_from_cfg():
    p = healthy()
    p["standouts"] = _standouts(n=30)
    assert ss.evaluate_all(p, None, now=NOW, cfg={})["ok"] is False          # default floor 40
    assert ss.evaluate_all(p, None, now=NOW, cfg={"floors": {"standouts": 20}})["ok"] is True


# ---------------------------------------------------------------------------
# loader + runner + baseline persistence (file I/O via tmp_path)
# ---------------------------------------------------------------------------

def _write_site(tmp: Path, payloads: dict) -> Path:
    site = tmp / "site"
    for s in ss.SURFACES:
        doc = payloads.get(s.key)
        if doc is None:
            continue
        p = site / s.path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc), encoding="utf-8")
    return site


def test_load_payloads_roundtrip(tmp_path):
    site = _write_site(tmp_path, healthy())
    loaded = ss.load_payloads(site)
    assert set(loaded) == {s.key for s in ss.SURFACES}
    rep = ss.evaluate_all(loaded, None, now=NOW, cfg={})
    assert rep["ok"] is True, rep["fail_reasons"]


def test_runner_dry_run_no_writes(tmp_path):
    site = _write_site(tmp_path, healthy())
    rep = runner.run(now=NOW, site_dir=site, dry_run=True)
    assert rep["ok"] is True
    assert "OK" in ss.summary_line(rep)


def test_baseline_idempotent_per_vintage(tmp_path):
    path = tmp_path / "baseline.jsonl"
    rows = ss.baseline_rows(ss.evaluate_all(healthy(), None, now=NOW, cfg={}))
    runner._update_baseline(path, [], rows)
    runner._update_baseline(path, runner._load_baseline(path), rows)   # re-run same vintage
    back = runner._load_baseline(path)
    keys = [(r["surface"], r["as_of"]) for r in back]
    assert len(keys) == len(set(keys)) == len(ss.SURFACES)   # one row per (surface, as_of), no dupes


def test_select_prior_skips_same_vintage():
    rows = [
        {"surface": "standouts", "as_of": "2026-06-19", "run_date": "2026-06-19", "fingerprint": "a"},
        {"surface": "standouts", "as_of": "2026-06-20", "run_date": "2026-06-20", "fingerprint": "b"},
    ]
    assert runner._select_prior(rows, "standouts", "2026-06-21")["as_of"] == "2026-06-20"
    assert runner._select_prior(rows, "standouts", "2026-06-20")["as_of"] == "2026-06-19"  # skip same vintage
    assert runner._select_prior(rows, "standouts", "2026-06-19")["as_of"] == "2026-06-20"
    assert runner._select_prior(rows, "missing", "2026-06-21") is None


def test_select_prior_ignores_late_replay_of_old_vintage():
    # a backfill carrying an OLD as_of but the NEWEST run_date must NOT become the comparand —
    # the previous DATA vintage (06-20) should win over the 06-10 replay.
    rows = [
        {"surface": "standouts", "as_of": "2026-06-20", "run_date": "2026-06-20", "fingerprint": "b"},
        {"surface": "standouts", "as_of": "2026-06-10", "run_date": "2026-06-25", "fingerprint": "replay"},
    ]
    assert runner._select_prior(rows, "standouts", "2026-06-26")["as_of"] == "2026-06-20"


# ---------------------------------------------------------------------------
# heartbeat integration — degrade-never-raise
# ---------------------------------------------------------------------------

def test_healthcheck_signal_sanity_never_raises():
    from scripts import healthcheck
    out = healthcheck.check_signal_sanity(NOW)
    assert set(out) == {"ok", "fail_reasons", "warnings"}
    assert isinstance(out["ok"], bool)


def test_healthcheck_signal_sanity_degrades_on_error(monkeypatch):
    from scripts import healthcheck
    monkeypatch.setattr(ss, "load_payloads", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = healthcheck.check_signal_sanity(NOW)
    assert out["ok"] is True                              # degrades, never fails liveness
    assert any("skipped" in w for w in out["warnings"])


def test_check_health_contract_unchanged():
    # the pure liveness function must be untouched by this change
    from scripts import healthcheck
    rep = healthcheck.check_health({"last_run": NOW.isoformat(), "circuit_breaker": {}}, NOW)
    assert set(rep) == {"ok", "fail_reasons", "warnings", "age_hours", "tripped"}
    assert rep["ok"] is True
