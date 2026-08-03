"""Desk thesis-ledger id discipline (engine.desk_ledger + every desk binding).

The 2026-08-03 experiments audit found desk thesis ids minted from the DATA date
(`{asof}-{i}`), not run identity: a stale state_asof re-briefed on later run days
collided with the prior run's ids, the scorers' last-wins dedupe silently discarded
58.9% of ai_desk's ledger, and stock_desk re-appended 35 graded ids with MUTATED
lean/check_by — un-pre-registering the falsifiers and breaking desk_placebo's
outcome pairing. Contract under test (docs/DESK_LEDGER_ID_MIGRATION.md):

  1. two runs over the SAME state_asof mint disjoint, run-scoped ids;
  2. an append that reuses a live id is rejected LOUDLY (::warning annotation at
     line start — the GitHub-annotation law) and the logged row is never mutated;
  3. the placebo null is printed beside the hit-rate in calibration notes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import desk_ledger as dl  # noqa: E402


# --------------------------------------------------------------------------- #
# run_token — the run identity every id now carries
# --------------------------------------------------------------------------- #
def test_run_token_is_the_full_utc_second():
    assert dl.run_token("2026-08-03T04:36:11.123456+00:00") == "20260803043611"
    # different run DAYS with the same time-of-day still yield distinct tokens —
    # the exact failure mode of the earlier HHMMSS-only slice
    a = dl.run_token("2026-08-03T04:36:11+00:00")
    b = dl.run_token("2026-08-04T04:36:11+00:00")
    assert a != b


def test_run_token_malformed_falls_back_empty():
    for bad in (None, "", "not-a-date", "2026-08"):
        assert dl.run_token(bad) == ""


# --------------------------------------------------------------------------- #
# ai_desk — two synthesize runs on the SAME state_asof mint disjoint ids
# --------------------------------------------------------------------------- #
def _ai_desk_brief(monkeypatch, when: str):
    from engine import ai_desk as d

    monkeypatch.setattr(d, "_now_iso", lambda: when)
    reply = {"regime_context": "x", "confidence": "low", "theses": [
        {"subject": "Energy", "lean": "overweight", "conviction": "low", "horizon_d": 20,
         "thesis": "t", "evidence": [], "dissent": "d", "falsifier_text": "f"},
        {"subject": "VIX", "lean": "fade-fear", "conviction": "low", "horizon_d": 10,
         "thesis": "t", "evidence": [], "dissent": "d", "falsifier_text": "f"},
    ]}
    state = {"as_of": "2026-06-15", "flow": None, "regime_snap": None, "track_record": None,
             "sources_present": {}}
    cfg = {**d._cfg(), "panel": {"enabled": False}}
    return d.synthesize(state, cfg, call=lambda s, u, c: (json.dumps(reply), None))


def test_ai_desk_two_runs_same_asof_disjoint_ids(monkeypatch):
    b1 = _ai_desk_brief(monkeypatch, "2026-08-03T04:36:11+00:00")
    b2 = _ai_desk_brief(monkeypatch, "2026-08-04T09:12:05+00:00")   # same state_asof, later run
    ids1 = {t["id"] for t in b1["theses"]}
    ids2 = {t["id"] for t in b2["theses"]}
    assert len(ids1) == 2 and len(ids2) == 2
    assert ids1.isdisjoint(ids2)
    # the id still leads with the asof date (radar_scorer's rid[:10] fallback contract)
    for tid in ids1 | ids2:
        assert tid[:10] == "2026-06-15"


# --------------------------------------------------------------------------- #
# thematic_desk — same contract, region-prefixed ids
# --------------------------------------------------------------------------- #
def _thematic_brief(monkeypatch, when: str):
    from engine import thematic_desk as td

    monkeypatch.setattr(td, "_now_iso", lambda: when)
    state = {"as_of": "2026-01-05", "region": "us", "market": "US",
             "narrative_rotation": {"region": "us", "guardrails": {}, "ranks": [
                 {"name": "AI Infra", "id": "ai", "rank": 1, "etf_proxy": "SMH",
                  "eligible": True, "scorable": True}]},
             "track_record": None}
    reply = {"regime_context": "x", "confidence": "low", "theses": [
        {"subject": "AI Infra", "lean": "overweight", "conviction": "low", "horizon_d": 20,
         "thesis": "t", "evidence": [], "dissent": "d", "falsifier_text": "f"}]}
    cfg = {**td._cfg(), "panel": {"enabled": False}}
    return td.synthesize(state, cfg, call=lambda s, u, c: (json.dumps(reply), None))


def test_thematic_two_runs_same_asof_disjoint_ids(monkeypatch):
    b1 = _thematic_brief(monkeypatch, "2026-08-03T04:36:11+00:00")
    b2 = _thematic_brief(monkeypatch, "2026-08-04T04:36:11+00:00")
    ids1 = {t["id"] for t in b1["theses"]}
    ids2 = {t["id"] for t in b2["theses"]}
    assert ids1 and ids2 and ids1.isdisjoint(ids2)
    for tid in ids1 | ids2:
        assert tid.startswith("us-2026-01-05-")


# --------------------------------------------------------------------------- #
# stock_desk — run-token threads through _build_note
# --------------------------------------------------------------------------- #
def test_stock_desk_notes_carry_the_run_token():
    from engine import stock_desk as sd

    nt = {"ticker": "HWM", "lean": "constructive", "conviction": "low", "horizon_d": 20,
          "thesis": "t", "evidence": [], "dissent": "d", "falsifier_text": "f"}
    pick = {"ticker": "HWM", "identity": {"name": "Howmet"}, "conviction": {}}
    a = sd._build_note(nt, pick, "2026-06-18", {}, 2, run_token="20260803043611")
    b = sd._build_note(nt, pick, "2026-06-18", {}, 2, run_token="20260804051200")
    assert a["id"] == "2026-06-18-HWM-20260803043611-3"
    assert b["id"] != a["id"]
    legacy = sd._build_note(nt, pick, "2026-06-18", {}, 2)
    assert legacy["id"] == "2026-06-18-HWM-3"          # tokenless fallback keeps legacy shape


# --------------------------------------------------------------------------- #
# immutability — an append reusing a live id is REFUSED, loudly, and the logged
# row's lean/check_by survive untouched (the stock_desk mutation defect, pinned)
# --------------------------------------------------------------------------- #
def _read_ledger(path: Path) -> list:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_reject_existing_ids_is_loud_and_first_wins(tmp_path, capsys):
    lp = tmp_path / "theses.jsonl"
    first = {"id": "2026-06-18-HWM-20260803043611-3", "lean": "cautious",
             "check_by": "2026-07-30"}
    kept = dl.reject_existing_ids(lp, [first], "stock_desk")
    assert kept == [first]                              # cold ledger: everything passes
    lp.write_text(json.dumps(first) + "\n")
    mutated = {"id": first["id"], "lean": "constructive", "check_by": "2026-07-16"}
    fresh = {"id": "2026-06-18-YETI-20260804051200-1", "lean": "cautious",
             "check_by": "2026-07-30"}
    kept = dl.reject_existing_ids(lp, [mutated, fresh], "stock_desk")
    assert kept == [fresh]                              # mutation refused, new id passes
    out = capsys.readouterr().out
    warn = [ln for ln in out.splitlines() if first["id"] in ln]
    assert warn and warn[0].startswith("::warning ")    # annotation STARTS the line (GH law)


def test_stock_desk_append_cannot_mutate_a_logged_row(tmp_path, capsys):
    from engine import stock_desk as sd

    note = {"id": "2026-06-22-YETI-20260803043611-6", "ticker": "YETI", "lean": "cautious",
            "conviction": "low", "horizon_d": 20, "check_by": "2026-07-21",
            "falsifier": {"text": "f", "check": {"kind": "soft"}}, "engine_verdict": None}
    sd._append_ledger([note], "2026-06-22", tmp_path)
    mutated = {**note, "lean": "constructive", "check_by": "2026-07-16"}
    sd._append_ledger([mutated], "2026-06-22", tmp_path)
    rows = _read_ledger(tmp_path / "data" / "stock_desk" / "theses.jsonl")
    assert len(rows) == 1                                # second append refused entirely
    assert rows[0]["lean"] == "cautious" and rows[0]["check_by"] == "2026-07-21"
    assert any(ln.startswith("::warning ") for ln in capsys.readouterr().out.splitlines())


def test_ai_desk_append_rejects_reused_id(tmp_path, capsys):
    from engine import ai_desk as d

    thesis = {"id": "2026-06-15-20260803043611-1", "subject": "Energy", "lean": "overweight",
              "conviction": "low", "horizon_d": 20, "check_by": "2026-07-14",
              "falsifier": {"text": "f", "check": {"kind": "soft"}}}
    brief = {"generated_at": "2026-08-03T04:36:11+00:00", "state_asof": "2026-06-15",
             "theses": [thesis]}
    d._append_ledger(brief, tmp_path)
    d._append_ledger({**brief, "theses": [{**thesis, "lean": "underweight"}]}, tmp_path)
    rows = _read_ledger(tmp_path / "data" / "ai_desk" / "theses.jsonl")
    assert len(rows) == 1 and rows[0]["lean"] == "overweight"
    assert any(ln.startswith("::warning ") for ln in capsys.readouterr().out.splitlines())


def test_thematic_append_first_wins_is_now_loud(tmp_path, capsys):
    from engine import thematic_desk as td

    thesis = {"id": "us-2026-01-05-20260803043611-1", "subject": "AI Infra",
              "lean": "overweight", "conviction": "low", "horizon_d": 20,
              "check_by": "2026-02-03", "falsifier": {"text": "f", "check": {"kind": "soft"}}}
    brief = {"market": "us", "state_asof": "2026-01-05", "theses": [thesis]}
    td._append_ledger(brief, tmp_path)
    td._append_ledger({**brief, "theses": [{**thesis, "check_by": "2026-01-20"}]}, tmp_path)
    rows = _read_ledger(tmp_path / "data" / "thematic_desk" / "theses.jsonl")
    assert len(rows) == 1 and rows[0]["check_by"] == "2026-02-03"
    assert any(ln.startswith("::warning ") for ln in capsys.readouterr().out.splitlines())


# --------------------------------------------------------------------------- #
# placebo null beside hit-rate — the un-nulled "hit-rate 0.889" fed the
# conviction-calibrating prompt as if one-half were the bar
# --------------------------------------------------------------------------- #
def _plant_summary(root: Path, slug: str, nh=0.81, nd=0.52):
    out = root / "data" / "calibration"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps({"desks": [
        {"slug": slug, "placebo_available": True, "null_hit_rate": nh, "null_dir_rate": nd}]}))


def test_placebo_lines_measured_and_absent(tmp_path):
    en, zh = dl.placebo_lines(tmp_path, "ai_desk")
    assert "not yet measured" in en and "尚未测得" in zh      # honest absence, never silent
    _plant_summary(tmp_path, "ai_desk")
    en, zh = dl.placebo_lines(tmp_path, "ai_desk")
    assert "0.81" in en and "not one-half" in en
    assert "0.81" in zh


def test_desk_scorer_prints_null_beside_hit_rate(tmp_path):
    from engine import ai_desk_scorer as s

    d = tmp_path / "data" / "ai_desk"
    d.mkdir(parents=True)
    ledger_row = {"id": "2026-06-15-20260803043611-1", "state_asof": "2026-06-15",
                  "subject": "Energy", "lean": "overweight", "conviction": "low",
                  "check_by": "2026-07-14",
                  "falsifier": {"text": "f", "check": {"kind": "rel_return"}}}
    scored_row = {"id": ledger_row["id"], "subject": "Energy", "lean": "overweight",
                  "conviction": "low", "kind": "rel_return", "outcome": "hit",
                  "realized": 0.02, "directionally_correct": True,
                  "scored_at": "2026-07-15T00:00:00+00:00"}
    (d / "theses.jsonl").write_text(json.dumps(ledger_row) + "\n")
    (d / "scored.jsonl").write_text(json.dumps(scored_row) + "\n")
    _plant_summary(tmp_path, "ai_desk")
    track = s.run(persist=False, root=tmp_path, today="2026-08-01")
    assert track["overall"]["n"] == 1
    note = track["calibration_note"]
    assert "hit-rate" in note and "0.81" in note and "not one-half" in note
    assert "0.81" in track["calibration_note_zh"]


def test_thematic_and_stock_notes_carry_the_null_line():
    from engine import stock_desk as sd
    from engine import thematic_desk as td

    overall = {"n": 9, "hits": 8, "misses": 1, "hit_rate": 0.889, "dir_accuracy": 0.667}
    line = "Chance alone would land a hit-rate near 0.81 on these exact conditions."
    for note in (td._calibration_note(overall, null_line=line),
                 sd._calibration_note(overall, null_line=line)):
        assert "0.889" in note and "0.81" in note
        assert note.index("0.889") < note.index("0.81")   # the null sits BESIDE the rate
