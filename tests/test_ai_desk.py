"""AI Desk (engine/ai_desk.py) — the accountable analyst layer, CONTEXT-ONLY.

Load-bearing invariants under test: it is NEVER scored (nothing in
axes/regime/conditions imports it); every kept thesis is a FALSIFIABLE direction
with an ENGINE-derived machine-checkable predicate (or an explicit 'soft' that the
scorer will skip — never fudged); malformed / non-directional model output is
dropped; the briefing bus degrades gracefully when a detector artifact is absent;
and the append-only ledger captures the entry levels a future scorer needs."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import ai_desk as d  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = d._cfg()


# --- helpers -------------------------------------------------------------- #
def _fake_call(reply_obj):
    """A drop-in for master_brain._call_model that returns canned JSON."""
    return lambda system, user, cfg: (json.dumps(reply_obj), None)


_GOOD_REPLY = {
    "regime_context": "Energy leads a stress cluster; breadth narrow.",
    "theses": [
        {"subject": "Energy", "lean": "overweight", "conviction": "Medium", "horizon_d": 20,
         "thesis": "Energy tops read_quality and anchors the dominant cluster.",
         "evidence": ["flow: Energy read_quality high", "cluster: Energy dominant"],
         "dissent": "Coincident, not predictive; crude could roll over.",
         "falsifier_text": "Energy lags SPY by >5% over 20 trading days."},
        {"subject": "VIX", "lean": "fade-fear", "conviction": "low", "horizon_d": 10,
         "thesis": "Relief snap firing out of a washout.",
         "evidence": ["regime_snap: status firing"],
         "dissent": "Verbal catalyst could reverse.",
         "falsifier_text": "VIX makes a new high above entry within 10 days."},
        {"subject": "retail", "lean": "overweight", "conviction": "low", "horizon_d": 20,
         "thesis": "basket subject — must resolve to a SOFT check.",
         "evidence": [], "dissent": "x", "falsifier_text": "y"},
        {"subject": "Energy", "lean": "banana", "conviction": "high", "horizon_d": 5,
         "thesis": "invalid lean — must be dropped.",
         "evidence": [], "dissent": "", "falsifier_text": ""},
    ],
    "confidence": "low",
}

_SYNTH_FLOW = {
    "as_of": "2026-06-16",
    "verdict": "display_only",
    "regime": {"vix": 16.0, "pctile": 0.3, "elevated": False},
    "cluster": {"absorption": 0.5, "regime": "mixed", "dominant_cluster": ["Energy"]},
    "sectors": [{"name": "Energy", "type": "sector", "read_quality": 0.7, "stage": "emerging",
                 "directional": False, "directional_confidence": "low"}],
    "baskets": [{"name": "Retail", "id": "retail", "type": "basket", "read_quality": 0.35}],
    "emerging": {"sectors": ["Energy"], "baskets": []},
    "cooling": {"sectors": [], "baskets": []},
    "ai_handoff": {"overall_verdict": "display_only",
                   "do_not_conclude": ["Do NOT infer forward returns from flow_score."],
                   "ai_directive": "FORBIDDEN: directional language unless validated.",
                   "caveats": ["c1", "c2"]},
}


def _tmp_root_with_flow(copy_parquets=True):
    tmp = Path(tempfile.mkdtemp())
    (tmp / "site" / "basketdata").mkdir(parents=True)
    (tmp / "site" / "basketdata" / "flow.json").write_text(json.dumps(_SYNTH_FLOW))
    if copy_parquets:
        (tmp / "data" / "yahoo").mkdir(parents=True)
        for tk in ("XLE", "SPY", "_VIX"):
            src = ROOT / "data" / "yahoo" / f"{tk}.parquet"
            if src.exists():
                shutil.copy(src, tmp / "data" / "yahoo" / f"{tk}.parquet")
    return tmp


# --- falsifier contract (the durability substrate) ------------------------ #
def test_gics_etf_map_resolves_to_real_parquets():
    for etf in d._GICS_ETF.values():
        assert (ROOT / "data" / "yahoo" / f"{etf}.parquet").exists(), etf
    assert (ROOT / "data" / "yahoo" / f"{d._BENCH}.parquet").exists()
    assert (ROOT / "data" / "yahoo" / f"{d._VIX}.parquet").exists()


def test_every_sector_lean_yields_a_machine_checkable_check():
    for sector in d._GICS_ETF:
        for lean in ("overweight", "underweight", "avoid"):
            chk = d._derive_check(sector, lean, 20, CFG)
            assert chk["kind"] == "rel_return"
            assert chk["subject_ticker"] == d._GICS_ETF[sector]
            assert chk["vs"] == d._BENCH
            assert chk["op"] in ("<", ">") and isinstance(chk["threshold"], float)
    # direction sign is correct: long lean is falsified by UNDERperformance, short by OVER
    assert d._derive_check("Energy", "overweight", 20, CFG)["op"] == "<"
    assert d._derive_check("Energy", "underweight", 20, CFG)["op"] == ">"


def test_fade_fear_is_a_vix_level_check_and_baskets_are_soft():
    fear = d._derive_check("VIX", "fade-fear", 10, CFG)
    assert fear["kind"] == "level" and fear["subject_ticker"] == d._VIX
    soft = d._derive_check("retail", "overweight", 20, CFG)
    assert soft["kind"] == "soft"                       # baskets aren't closeable -> unscored


def test_check_by_is_a_future_business_day():
    import pandas as pd
    out = d._check_by("2026-06-19", 1)                  # Friday + 1 BDay -> a Monday
    ts = pd.Timestamp(out)
    assert ts > pd.Timestamp("2026-06-19") and ts.weekday() < 5


# --- the analyst: parse / validate / drop -------------------------------- #
def test_synthesize_validates_and_drops_bad_theses():
    state = d.gather_desk_state(_tmp_root_with_flow(copy_parquets=False))
    brief = d.synthesize(state, CFG, call=_fake_call(_GOOD_REPLY))
    assert brief["schema"] == "ai_desk.v1" and brief["is_context_only"] is True
    # 4 in -> invalid 'banana' lean dropped, 3 kept (incl. the soft basket)
    assert len(brief["theses"]) == 3
    subjects = [t["subject"] for t in brief["theses"]]
    assert "Energy" in subjects and "VIX" in subjects and "retail" in subjects
    ids = [t["id"] for t in brief["theses"]]
    assert ids == [f"2026-06-16-{i}" for i in (1, 2, 3)]          # sequential, no gaps
    for t in brief["theses"]:
        assert t["lean"] in d._THESIS_LEANS
        assert "check" in t["falsifier"] and t["check_by"]        # every thesis is falsifiable
        assert t["conviction"] in d._CONVICTIONS                  # "Medium" -> "medium"


def test_synthesize_degrades_when_model_unavailable():
    state = d.gather_desk_state(_tmp_root_with_flow(copy_parquets=False))
    brief = d.synthesize(state, CFG, call=lambda s, u, c: (None, "no_client_or_key"))
    assert brief["theses"] == [] and brief["degraded_reason"] == "no_client_or_key"
    assert brief["is_context_only"] is True                        # invariant holds even degraded


def test_non_directional_lean_is_not_a_thesis():
    assert d._build_thesis({"subject": "Energy", "lean": "neutral"}, 0, "2026-06-16", CFG) is None
    assert d._build_thesis({"subject": "", "lean": "overweight"}, 0, "2026-06-16", CFG) is None


# --- the briefing bus: graceful degradation ------------------------------ #
def test_gather_state_degrades_gracefully():
    # flow only -> regime_snap omitted, sources flagged
    st = d.gather_desk_state(_tmp_root_with_flow(copy_parquets=False))
    assert st["sources_present"] == {"flow": True, "regime_snap": False}
    assert st["flow"] and st["regime_snap"] is None and st["track_record"] is None
    # neither artifact -> None (nothing to brief on)
    assert d.gather_desk_state(Path(tempfile.mkdtemp())) is None


# --- the ledger: one scorable row per thesis ----------------------------- #
def test_ledger_appends_one_row_per_thesis_with_entry_levels():
    root = _tmp_root_with_flow(copy_parquets=True)
    state = d.gather_desk_state(root)
    brief = d.synthesize(state, CFG, call=_fake_call(_GOOD_REPLY))
    d._append_ledger(brief, root)
    rows = [json.loads(line) for line in (root / "data" / "ai_desk" / "theses.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    for r in rows:
        assert r["status"] == "open" and r["outcome"] is None
        assert "check" in r["falsifier"] and r["check_by"]
    energy = next(r for r in rows if r["subject"] == "Energy")
    assert "XLE" in energy["entry_levels"] and "SPY" in energy["entry_levels"]
    vix = next(r for r in rows if r["subject"] == "VIX")
    assert "_VIX" in vix["entry_levels"]


# --- end to end: display-only, persists artifacts, never raises ----------- #
def test_run_persists_artifacts_and_is_display_only():
    root = _tmp_root_with_flow(copy_parquets=True)
    brief = d.run(persist=True, root=root, force=True, call=_fake_call(_GOOD_REPLY))
    assert brief and brief["is_context_only"] is True
    assert (root / "data" / "regime" / "ai_desk.json").exists()
    pub = json.loads((root / "site" / "ai_desk.json").read_text())
    assert "raw_text" not in pub                          # public copy strips the raw model reply
    assert (root / "data" / "ai_desk" / "theses.jsonl").exists()
    # no artifacts at all -> run returns None, never raises
    assert d.run(persist=True, root=Path(tempfile.mkdtemp()), force=True,
                 call=_fake_call(_GOOD_REPLY)) is None


# --- the never-scored invariant ------------------------------------------ #
def test_never_scored_invariant():
    for mod in ("engine/axes.py", "engine/regime.py", "engine/conditions.py"):
        assert "ai_desk" not in (ROOT / mod).read_text(), f"{mod} must not import ai_desk"
