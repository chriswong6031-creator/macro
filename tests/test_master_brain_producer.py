"""master_brain PRODUCER half — the brain stakes its OWN falsifiable cross-asset leans.

Proves the addition is ADDITIVE (free-text byte-identical with theses absent AND present),
that a theses bug can never lose the narrative (own-try), the falsifier derivation +
validation mirror ai_desk, the cache-presence gate forces soft (not a zombie 'expired'),
non-macro lenses emit nothing, and master_brain doesn't import ai_desk at module top (no
cycle). All stub-based — no live LLM.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import master_brain as mb  # noqa: E402

ASOF = "2026-01-05"
STATE = {"macro": {"date": ASOF, "quad": "Q1"}}
CFG = {"llm_model": "deepseek-v4-pro"}
_FREE_TEXT = {
    "summary": "Goldilocks but liquidity contracting.",
    "regime_read": "Macro Q1, low macro-risk; FX risk-on.",
    "conflicts": ["FX risk-on vs contracting liquidity"],
    "rotation_check": "Partly tracking.",
    "transmission": ["liquidity drain -> crypto first"],
    "watch_items": ["FOMC Jun 17"], "confidence": "medium"}


def _mk_parquet(root, ticker, points):
    d = root / "data" / "yahoo"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.to_datetime([p[0] for p in points])
    pd.DataFrame({"close": [p[1] for p in points], "volume": [1] * len(points)},
                 index=idx).to_parquet(d / f"{ticker}.parquet")


def _stub(reply_obj):
    mb._call_model = lambda system, user, cfg: (json.dumps(reply_obj), None)


# --- falsifier derivation (root=None → trust the static map; cache-gate off) ------ #
def test_derive_rel_return_underweight():
    c = mb._mb_derive_check("High-yield credit", "underweight", 20, None)
    assert c == {"kind": "rel_return", "subject_ticker": "HYG", "vs": "SPY",
                 "op": ">", "threshold": 0.05, "horizon_d": 20}


def test_derive_rel_return_overweight_uses_negative_threshold():
    c = mb._mb_derive_check("Semiconductors", "overweight", 30, None)
    assert c["subject_ticker"] == "SMH" and c["op"] == "<" and c["threshold"] == -0.05


def test_fade_fear_derives_level_check():
    c = mb._mb_derive_check("VIX", "fade-fear", 20, None)
    assert c["kind"] == "level" and c["subject_ticker"] == "_VIX" and c["op"] == ">"
    assert c["ref"] == "entry"


def test_unknown_subject_is_soft():
    assert mb._mb_derive_check("Frontier markets", "overweight", 20, None)["kind"] == "soft"


def test_cache_gate_forces_soft_not_expired():
    """A subject whose ticker isn't on disk → soft (logged-unscored), never a 10-BD zombie."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _mk_parquet(root, "SPY", [(ASOF, 100.0)])      # SPY present, SMH absent
        c = mb._mb_derive_check("Semiconductors", "overweight", 20, root)
        assert c["kind"] == "soft" and "not in price cache" in c["reason"]
        c2 = mb._mb_derive_check("US equities", "overweight", 20, root)   # SPY cached
        assert c2["kind"] == "rel_return"


def test_build_thesis_validates_and_coerces():
    th = mb._mb_build_thesis({"subject": "Long Treasuries", "lean": "OVERWEIGHT",
                              "horizon_d": 999, "conviction": "enormous"}, 0, ASOF, None, CFG)
    assert th["id"] == f"mb-{ASOF}-1" and th["horizon_d"] == 60 and th["conviction"] == "low"
    assert th["falsifier"]["check"]["subject_ticker"] == "TLT"


def test_build_thesis_drops_bad_lean():
    assert mb._mb_build_thesis({"subject": "Small caps", "lean": "buy"}, 0, ASOF, None, CFG) is None


# --- synthesize: additive byte-identity + own-try ------------------------------- #
def test_synthesize_theses_absent_is_additive():
    _stub(dict(_FREE_TEXT))                              # no 'theses' key
    b = mb.synthesize(STATE, CFG, lens="macro", root=None)
    for k, v in _FREE_TEXT.items():
        assert b[k] == v                                # free-text untouched
    assert b["theses"] == []                            # key always present


def test_synthesize_theses_present_keeps_free_text_byte_identical():
    base = mb.synthesize(STATE, (_stub(dict(_FREE_TEXT)) or CFG), lens="macro", root=None)
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _mk_parquet(root, "HYG", [(ASOF, 100.0)])
        _mk_parquet(root, "SPY", [(ASOF, 100.0)])
        _stub({**_FREE_TEXT, "theses": [{"subject": "High-yield credit", "lean": "underweight",
                                         "conviction": "high", "horizon_d": 20,
                                         "thesis": "credit cracking", "falsifier_text": "HY rallies"}]})
        b = mb.synthesize(STATE, CFG, lens="macro", root=root)
    for k in _FREE_TEXT:
        assert b[k] == base[k]                          # narrative unchanged by adding a thesis
    assert len(b["theses"]) == 1 and b["theses"][0]["id"].startswith("mb-")
    assert b["theses"][0]["falsifier"]["check"]["subject_ticker"] == "HYG"


def test_synthesize_garbage_theses_preserves_free_text():
    _stub({**_FREE_TEXT, "theses": "not-a-list"})
    b = mb.synthesize(STATE, CFG, lens="macro", root=None)
    assert b["summary"] == _FREE_TEXT["summary"] and b["theses"] == []


def test_bad_max_theses_cfg_does_not_lose_free_text():
    _stub({**_FREE_TEXT, "theses": [{"subject": "Small caps", "lean": "overweight"}]})
    b = mb.synthesize(STATE, {**CFG, "max_theses": "foo"}, lens="macro", root=None)
    assert b["regime_read"] == _FREE_TEXT["regime_read"] and b["theses"] == []


def test_non_macro_lens_emits_no_theses():
    _stub({**_FREE_TEXT, "theses": [{"subject": "China equities", "lean": "overweight"}]})
    b = mb.synthesize({"china": {"date": ASOF}}, CFG, lens="china", root=None)
    assert b["theses"] == []


def test_emit_theses_gate_off():
    _stub({**_FREE_TEXT, "theses": [{"subject": "Small caps", "lean": "overweight"}]})
    b = mb.synthesize(STATE, {**CFG, "emit_theses": False}, lens="macro", root=None)
    assert b["theses"] == []


# --- ledger append ------------------------------------------------------------- #
def test_append_ledger_writes_row_and_never_raises():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        brief = {"generated_at": "2026-01-05T00:00:00Z", "state_asof": ASOF, "theses": [
            mb._mb_build_thesis({"subject": "Long Treasuries", "lean": "overweight",
                                 "conviction": "low"}, 0, ASOF, None, CFG)]}
        mb._append_ledger(brief, root)                  # no price cache → entry_levels empty, no raise
        rows = (root / "data" / "master_brain" / "theses.jsonl").read_text().splitlines()
        row = json.loads(rows[0])
        assert row["id"] == f"mb-{ASOF}-1" and row["status"] == "open"
        assert row["subject"] == "Long Treasuries" and "regime" in row
        mb._append_ledger({"theses": []}, root)         # empty → no-op, no raise


def test_run_macro_appends_china_does_not(monkeypatch):
    _stub({**_FREE_TEXT, "theses": [{"subject": "Long Treasuries", "lean": "overweight"}]})
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "data" / "regime").mkdir(parents=True)
        (root / "data" / "regime" / "latest.json").write_text(json.dumps({"date": ASOF}))
        monkeypatch.setattr(mb, "_cfg", lambda: {"enabled": True, "llm_model": "x"})
        monkeypatch.setattr(mb, "gather_state", lambda r: STATE)
        monkeypatch.setattr(mb, "gather_china_state", lambda r: {"china": {"date": ASOF}})
        mb.run(persist=True, root=root, force=True, lens="macro")
        assert (root / "data" / "master_brain" / "theses.jsonl").exists()
        mb.run(persist=True, root=root, force=True, lens="china")
        # china writes its own brief but NO master_brain ledger growth from the china lens
        n = len((root / "data" / "master_brain" / "theses.jsonl").read_text().splitlines())
        assert n == 1


def test_master_brain_import_has_no_top_level_ai_desk_cycle():
    """Importing master_brain ALONE must not pull engine.ai_desk (it imports master_brain)."""
    code = ("import sys; import engine.master_brain; "
            "assert 'engine.ai_desk' not in sys.modules, 'cycle: ai_desk imported at top'")
    r = subprocess.run([sys.executable, "-c", code],
                       cwd=str(Path(__file__).resolve().parent.parent),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
