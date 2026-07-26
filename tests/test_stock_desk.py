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


# --------------------------------------------------------------------------- #
# scored.jsonl — the per-thesis outcome spine engine.spine._DESK_SCORED already
# registered for this desk but nothing wrote. Without it the desk's 45 decided
# outcomes never reach engine.desk_scorer.desk_weights, and the cross-desk pooling
# "family" it shrinks toward is a single member (ai_desk) in practice.
# --------------------------------------------------------------------------- #
def _ledger(tmp_path, rows):
    d = tmp_path / "data" / "stock_desk"
    d.mkdir(parents=True, exist_ok=True)
    (tmp_path / "site" / "stockdata").mkdir(parents=True, exist_ok=True)
    (d / "theses.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


def _row(tid, ticker="AAA", check_by="2026-02-15", kind="rel_return"):
    return {"id": tid, "ticker": ticker, "lean": "constructive", "conviction": "medium",
            "state_asof": "2026-01-05", "check_by": check_by,
            "falsifier": {"check": {"kind": kind, "subject_ticker": ticker, "vs": "SPY",
                                    "op": "<", "threshold": -0.05, "horizon_d": 20}},
            "entry_levels": {ticker: 100.0, "SPY": 100.0}}


def _series(lo=130.0):
    """name lo% vs SPY +5% over the window — a HIT at lo=130, a MISS at lo=100."""
    idx = pd.date_range("2026-01-01", periods=60, freq="B")
    name = pd.Series(np.linspace(100, lo, 60), index=idx)
    spy = pd.Series(np.linspace(100, 105, 60), index=idx)
    return lambda t: spy if t == "SPY" else name


def test_scorer_persists_per_thesis_outcomes(monkeypatch, tmp_path):
    monkeypatch.setattr(sd, "_stock_series", _series())
    d = _ledger(tmp_path, [_row("s-1"), _row("s-2", check_by="2099-01-01"),
                           _row("s-3", kind="soft")])
    sd.score_ledger(root=tmp_path, today="2026-03-01")
    by_id = {r["id"]: r for r in
             (json.loads(x) for x in (d / "scored.jsonl").read_text().splitlines())}
    assert by_id["s-1"]["outcome"] == "hit" and by_id["s-1"]["realized"] is not None
    assert by_id["s-3"]["outcome"] == "unscored"
    assert "s-2" not in by_id             # still open — a verdict it has not reached yet
    assert by_id["s-1"]["scored_at"]      # auditable, like every other desk's spine


def test_scored_row_carries_subject_so_the_spine_does_not_collapse_the_desk(monkeypatch, tmp_path):
    """engine.spine.adapt_desk_scorer reads `subject` for the row's symbol, and event_key
    defaults to "{symbol}:{as_of}". This desk's ledger keys on `ticker`, so without a
    `subject` alias every row falls back to the literal "stock_desk" and every lean sharing
    a check_by date collapses to ONE effective event in engine.pooling.arming — on the live
    ledger that is 8 events instead of 36."""
    monkeypatch.setattr(sd, "_stock_series", _series())
    d = _ledger(tmp_path, [_row("s-1", ticker="AAA"), _row("s-2", ticker="BBB")])
    sd.score_ledger(root=tmp_path, today="2026-03-01")
    rows = [json.loads(x) for x in (d / "scored.jsonl").read_text().splitlines()]
    assert {r["subject"] for r in rows} == {"AAA", "BBB"}
    assert all(r["subject"] == r["ticker"] for r in rows)
    from engine import spine
    got = spine.adapt_desk_scorer(
        root=tmp_path, desks={"stock_desk": spine._DESK_SCORED["stock_desk"]})
    assert len({r.event_key for r in got}) == 2      # two names → two effective events


def test_scored_ledger_is_append_only_and_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(sd, "_stock_series", _series())
    d = _ledger(tmp_path, [_row("s-1")])
    first = sd.score_ledger(root=tmp_path, today="2026-03-01")
    lines = (d / "scored.jsonl").read_text()
    again = sd.score_ledger(root=tmp_path, today="2026-03-01")
    assert (d / "scored.jsonl").read_text() == lines   # no duplicate row for a graded id
    assert again["overall"] == first["overall"]


def test_a_published_verdict_is_not_rewritten_by_a_re_based_history(monkeypatch, tmp_path):
    """yfinance re-adjusts a name's WHOLE stored series on every dividend, so re-grading
    from live prices can silently flip a verdict the track record already reported. The
    graded outcome is the published one."""
    monkeypatch.setattr(sd, "_stock_series", _series())
    d = _ledger(tmp_path, [_row("s-1")])
    assert sd.score_ledger(root=tmp_path, today="2026-03-01")["overall"]["hits"] == 1
    monkeypatch.setattr(sd, "_stock_series", _series(lo=100.0))   # re-based down → would MISS
    again = sd.score_ledger(root=tmp_path, today="2026-03-01")
    assert again["overall"]["hits"] == 1 and again["overall"]["misses"] == 0
    rows = [json.loads(x) for x in (d / "scored.jsonl").read_text().splitlines()]
    assert [r["outcome"] for r in rows] == ["hit"]    # one row, still the published verdict


def test_unpriceable_lean_stays_retryable(monkeypatch, tmp_path):
    """`expired` is NOT frozen. This desk emits it on the FIRST unpriceable read, with none
    of engine.desk_scorer.GRACE_BD's ten business days of slack — freezing it would turn a
    collector gap (a name missing from today's `_closes()` panel) into a permanent verdict."""
    monkeypatch.setattr(sd, "_stock_series", lambda t: None)
    d = _ledger(tmp_path, [_row("s-1")])
    assert sd.score_ledger(root=tmp_path, today="2026-03-01")["scored_total"] == 0
    assert not (d / "scored.jsonl").exists()          # nothing final to write
    monkeypatch.setattr(sd, "_stock_series", _series())   # the collector backfills
    assert sd.score_ledger(root=tmp_path, today="2026-03-01")["overall"]["hits"] == 1


def test_track_record_is_unchanged_by_the_new_spine(monkeypatch, tmp_path):
    """The scored spine is ADDITIVE: the aggregate the Calibration Hub and the site panel
    read must be identical whether the outcomes are freshly graded or read back."""
    monkeypatch.setattr(sd, "_stock_series", _series())
    _ledger(tmp_path, [_row("s-1"), _row("s-2", ticker="BBB"),
                       _row("s-3", check_by="2099-01-01"), _row("s-4", kind="soft")])
    first = sd.score_ledger(root=tmp_path, today="2026-03-01")
    second = sd.score_ledger(root=tmp_path, today="2026-03-01")
    for k in ("scored_total", "open", "unscored_neutral", "overall", "by_lean",
              "by_conviction", "calibration_note"):
        assert first[k] == second[k], k
