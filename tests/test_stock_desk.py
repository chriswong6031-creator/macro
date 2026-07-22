"""Stock desk (engine.stock_desk) — accountable AI judgment layer on the US top picks.

Verify the falsifiable-lean contract without any API key (mock `call`): a constructive
lean → a rel_return check FALSE if it lags SPY; cautious/avoid mirror the threshold;
neutral → soft/unscored; the deterministic risk reshape CLAMPS a constructive lean on a
flagged name down to cautious (the AI can never re-introduce the chase); the scorer grades
a past-due lean hit/miss vs realized name-minus-SPY return; and it degrades gracefully.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from engine import stock_desk as sd


# NOTE: the conviction shape here mirrors the REAL engine/stock_score.profile() schema —
# cycle_blocked (NOT 'blocked'/'size'/'risk'), verdict, band, cautions. Earlier fixtures
# used a synthetic {blocked, size} shape that masked the inert-guard bug (the reviewer's
# finding); these now match production so the clamp tests actually exercise the guard.
def _state():
    return {"as_of": "2026-01-05",
            "picks": [{"ticker": "AAA", "identity": {"name": "Alpha"},
                       "conviction": {"verdict": "Leader · good entry", "band": "buy",
                                      "cycle_blocked": False}}],
            "track_record": None}


def _mock(notes):
    def call(system, user, cfg):
        return json.dumps({"notes": notes}), None
    return call


def _note(ticker="AAA", lean="constructive", **kw):
    base = {"ticker": ticker, "lean": lean, "conviction": "medium", "horizon_d": 20,
            "thesis": "t", "evidence": ["e"], "dissent": "d", "falsifier_text": "f"}
    base.update(kw)
    return base


def test_constructive_yields_rel_return_check():
    syn = sd.synthesize(_state(), call=_mock([_note(lean="constructive")]))
    nt = sd._build_note(syn["notes"][0], _state()["picks"][0], "2026-01-05", sd._cfg(), 0)
    chk = nt["falsifier"]["check"]
    assert chk["kind"] == "rel_return" and chk["subject_ticker"] == "AAA" and chk["vs"] == "SPY"
    assert chk["op"] == "<" and chk["threshold"] == -0.05      # FALSE if it lags SPY by ≥5%
    assert nt["check_by"] and nt["lean"] == "constructive"


def test_cautious_mirrors_threshold():
    # A cautious lean on a genuinely WEAK / lagging name STAYS cautious → mirrored short check.
    # (On a strong-leader name it now softens to neutral — see the Phase 3 tests below.)
    weak = {"ticker": "AAA", "conviction": {"verdict": "Lagging — relative weakness",
                                            "band": "watch", "cycle_blocked": False}}
    nt = sd._build_note(_note(lean="cautious"), weak, "2026-01-05", sd._cfg(), 0)
    chk = nt["falsifier"]["check"]
    assert chk["op"] == ">" and chk["threshold"] == 0.05       # FALSE if it OUTperforms by ≥5%
    assert nt["lean"] == "cautious"


def test_cautious_on_leader_extension_softens_to_neutral():
    """Phase 3: a 'cautious' lean is a graded directional SHORT vs SPY. On a strong LEADER
    that is merely extended it fights live momentum — only ~17% directionally correct on this
    desk (n=52) vs ~86% on genuinely weak names (n=7). So soften cautious-on-a-leader to
    NEUTRAL (watch, don't chase, DON'T short); the winning weak-name cautions are untouched."""
    # _state()'s pick is "Leader · good entry" (a strong-leader-extension).
    nt = sd._build_note(_note(lean="cautious"), _state()["picks"][0], "2026-01-05", sd._cfg(), 0)
    assert nt["lean"] == "neutral"                             # leader + extended → neutral, not a short
    assert nt["falsifier"]["check"]["kind"] == "soft"         # neutral ⇒ unscored (no losing short logged)
    assert "soften" in (nt["dissent"] or "").lower()


def test_constructive_on_leader_extension_clamps_to_neutral_not_cautious():
    """The anti-chase clamp on a risk-blocked STRONG LEADER de-escalates to NEUTRAL (don't
    chase, don't short) — NOT cautious. Only a bearish-tape name clamps down to cautious."""
    pick = {"ticker": "DDD",
            "conviction": {"verdict": "High-conviction leader — good entry", "band": "buy",
                           "cycle_blocked": False, "cautions": ["extended +18% over 50dma"]}}
    nt = sd._build_note(_note(ticker="DDD", lean="constructive"), pick, "2026-01-05", sd._cfg(), 0)
    assert nt["lean"] == "neutral"                            # leader-extension ⇒ neutral, not cautious
    assert nt["falsifier"]["check"]["kind"] == "soft"


def test_avoid_on_leader_extension_also_softens_to_neutral():
    """De-escalation is symmetric: an 'avoid' (the strongest short) on a leader-extension also
    softens to neutral — the reshape never lets the desk short a momentum-intact leader."""
    nt = sd._build_note(_note(lean="avoid"), _state()["picks"][0], "2026-01-05", sd._cfg(), 0)
    assert nt["lean"] == "neutral"


def test_neutral_is_soft_unscored():
    nt = sd._build_note(_note(lean="neutral"), _state()["picks"][0], "2026-01-05", sd._cfg(), 0)
    assert nt["falsifier"]["check"]["kind"] == "soft"


def test_risk_reshape_clamps_constructive_on_extended_name():
    """The CASY guard: an Extended/'don't chase' verdict can never be promoted to
    constructive by the AI — it is clamped down to cautious via the word-scan."""
    blocked = {"ticker": "BBB", "identity": {"name": "Beta"},
               "conviction": {"verdict": "Extended — don't chase", "band": "watch",
                              "cycle_blocked": False,
                              "cautions": ["extended +31% over 200dma — chasing"]}}
    nt = sd._build_note(_note(ticker="BBB", lean="constructive"), blocked, "2026-01-05", sd._cfg(), 0)
    assert nt["lean"] == "cautious"                            # clamped, not constructive
    assert nt["falsifier"]["check"]["op"] == ">"               # check follows the clamped lean
    assert "clamped" in (nt["dissent"] or "")


def test_cycle_blocked_real_schema_clamps_constructive():
    """REGRESSION (the inert-guard bug): the production profile carries `cycle_blocked`
    (NOT 'blocked'), and the cycle-blocked verdict 'Strong name · wrong tape — wait for a
    base' has NO extended/avoid trigger word — the word-scan alone misses it. The
    cycle_blocked check must clamp it. This is the exact shape of 21/120 live board names."""
    pick = {"ticker": "AMAT", "identity": {"name": "Applied Materials"},
            "conviction": {"verdict": "Strong name · wrong tape — wait for a base",
                           "band": "watch", "trust_tier": "context",
                           "cycle_blocked": True, "cautions": ["cycle: NEARING A HIGH"]}}
    nt = sd._build_note(_note(ticker="AMAT", lean="constructive"), pick, "2026-01-05", sd._cfg(), 0)
    assert nt["lean"] == "cautious"                            # cycle_blocked → clamped
    assert nt["falsifier"]["check"]["op"] == ">"


def test_avoid_verdict_text_also_clamps():
    flagged = {"ticker": "CCC", "conviction": {"verdict": "Avoid — exit", "band": "avoid",
                                               "cycle_blocked": False}}
    nt = sd._build_note(_note(ticker="CCC", lean="constructive"), flagged, "2026-01-05", sd._cfg(), 0)
    assert nt["lean"] == "cautious"


def test_degrades_when_llm_unavailable():
    syn = sd.synthesize(_state(), call=lambda s, u, c: (None, "no_client_or_key"))
    assert syn["notes"] == [] and syn["degraded"] == "no_client_or_key"


def test_scorer_grades_constructive_hit(monkeypatch, tmp_path):
    # name +30%, SPY +5% over the window → constructive (FALSE if it lags) is a HIT
    idx = pd.date_range("2026-01-01", periods=60, freq="B")
    name = pd.Series(np.linspace(100, 130, 60), index=idx)
    spy = pd.Series(np.linspace(100, 105, 60), index=idx)
    monkeypatch.setattr(sd, "_stock_series", lambda t: name if t == "AAA" else spy)
    led = tmp_path / "data" / "stock_desk"
    led.mkdir(parents=True)
    (tmp_path / "site" / "stockdata").mkdir(parents=True)
    row = {"id": "2026-01-05-AAA-1", "ticker": "AAA", "lean": "constructive",
           "conviction": "medium", "state_asof": "2026-01-05", "check_by": "2026-02-15",
           "falsifier": {"check": {"kind": "rel_return", "subject_ticker": "AAA", "vs": "SPY",
                                   "op": "<", "threshold": -0.05, "horizon_d": 20}},
           "entry_levels": {"AAA": 100.0, "SPY": 100.0}}
    (led / "theses.jsonl").write_text(json.dumps(row) + "\n")
    tr = sd.score_ledger(root=tmp_path, today="2026-03-01")
    assert tr["scored_total"] == 1 and tr["overall"]["hits"] == 1
    assert tr["by_lean"]["constructive"]["n"] == 1 and tr["recent"][0]["outcome"] == "hit"


def test_scorer_grades_constructive_miss(monkeypatch, tmp_path):
    # name flat, SPY +10% → constructive lags by ≥5% → MISS
    idx = pd.date_range("2026-01-01", periods=60, freq="B")
    name = pd.Series(np.linspace(100, 100, 60), index=idx)
    spy = pd.Series(np.linspace(100, 110, 60), index=idx)
    monkeypatch.setattr(sd, "_stock_series", lambda t: name if t == "AAA" else spy)
    led = tmp_path / "data" / "stock_desk"
    led.mkdir(parents=True)
    (tmp_path / "site" / "stockdata").mkdir(parents=True)
    row = {"id": "2026-01-05-AAA-1", "ticker": "AAA", "lean": "constructive",
           "conviction": "low", "state_asof": "2026-01-05", "check_by": "2026-02-15",
           "falsifier": {"check": {"kind": "rel_return", "subject_ticker": "AAA", "vs": "SPY",
                                   "op": "<", "threshold": -0.05, "horizon_d": 20}},
           "entry_levels": {"AAA": 100.0, "SPY": 100.0}}
    (led / "theses.jsonl").write_text(json.dumps(row) + "\n")
    tr = sd.score_ledger(root=tmp_path, today="2026-03-01")
    assert tr["overall"]["misses"] == 1


def test_scorer_open_until_check_by(tmp_path):
    led = tmp_path / "data" / "stock_desk"
    led.mkdir(parents=True)
    (tmp_path / "site" / "stockdata").mkdir(parents=True)
    row = {"id": "2026-01-05-AAA-1", "ticker": "AAA", "lean": "constructive", "conviction": "low",
           "check_by": "2099-01-01",
           "falsifier": {"check": {"kind": "rel_return", "subject_ticker": "AAA", "vs": "SPY",
                                   "op": "<", "threshold": -0.05}}}
    (led / "theses.jsonl").write_text(json.dumps(row) + "\n")
    tr = sd.score_ledger(root=tmp_path, today="2026-03-01")
    assert tr["open"] == 1 and tr["scored_total"] == 0
