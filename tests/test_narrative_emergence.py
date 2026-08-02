"""Forming-narrative desk (engine.narrative_emergence + engine.emergence_alerts).

Pure-logic tests: the transparent 0–100 score is tightening-led and monotone, recommended
tickers are ranked clean-entry-first (least-extended), the constituent-set signature is
stable + order-independent, and the alert engine seeds silently then fires once per NEW
narrative above the bar (jsonl round-trip dedups by id). No network, no caches.
"""
from __future__ import annotations

from engine import emergence_alerts as ea
from engine import narrative_emergence as ne
from lib import config


def _cand(n=8, cohesion=0.55, chg=0.30, mom=0.10, label="Cross-sector",
          top_sector="Industrials", top_share=0.4, overlap=0.0, ipo=False,
          tickers=("AAA", "BBB", "CCC", "DDD", "EEE")):
    return {"n": n, "cohesion": cohesion, "cohesion_chg": chg, "mom_window": mom,
            "label": label, "top_sector": top_sector, "top_sector_share": top_share,
            "basket_overlap": overlap, "ipo_wave": ipo, "recent_ipos": [],
            "constituents": [{"ticker": t, "name": t + " Inc", "sector": top_sector}
                             for t in tickers]}


# ----------------------------------------------------------------- scoring
def test_score_is_tightening_led_and_monotone():
    base = ne._legs(_cand(chg=0.05))
    tight = ne._legs(_cand(chg=0.30))
    # more tightening (the "forming" signal) must not lower the score, and should raise it
    assert ne._emergence_score(tight) > ne._emergence_score(base)
    # tightening carries the largest weight
    assert ne._W["tighten"] == max(ne._W.values())


def test_legs_are_clipped_unit_interval():
    legs = ne._legs(_cand(cohesion=0.99, chg=0.99, mom=0.99))
    assert all(0.0 <= v <= 1.0 for v in legs.values())


def test_score_label_bands():
    assert ne._score_label(70)["css"] == "ne-hot"
    assert ne._score_label(55)["css"] == "ne-warm"
    assert ne._score_label(45)["css"] == "ne-early"
    assert ne._score_label(10)["css"] == "ne-faint"


# ----------------------------------------------------------------- recommended tickers
def test_recommended_ranks_clean_entry_first():
    cand = _cand(tickers=("HOT", "OK", "CALM"))
    ext = {"HOT": {"grade": "parabolic", "ext": 80.0, "ext_z": 3.1},
           "OK": {"grade": "steady", "ext": 5.0, "ext_z": 0.2},
           "CALM": {"grade": "intrend", "ext": -10.0, "ext_z": -0.4}}
    rows, stretched = ne._recommended(cand, ext)
    order = [r["ticker"] for r in rows]
    # intrend (cleanest entry) leads; parabolic (chase) sinks to the bottom
    assert order[0] == "CALM" and order[-1] == "HOT"
    assert stretched == round(1 / 3, 2)            # one of three is stretched/parabolic


def test_recommended_degrades_without_extension():
    rows, stretched = ne._recommended(_cand(tickers=("X", "Y")), {})
    assert {r["grade"] for r in rows} == {"na"} and stretched == 0.0


# ----------------------------------------------------------------- signature
def test_signature_stable_and_order_independent():
    a = ne._signature(_cand(tickers=("MSFT", "AAPL", "NVDA")))
    b = ne._signature(_cand(tickers=("NVDA", "MSFT", "AAPL")))   # reordered
    c = ne._signature(_cand(tickers=("MSFT", "AAPL", "TSLA")))   # one swapped
    assert a == b and a != c and len(a) == 12


# ----------------------------------------------------------------- alert engine
def _emergence(narratives, region="us", as_of="2026-06-18"):
    return {"region": region, "as_of": as_of, "narratives": narratives}


def _nv(sig, score=66, name="Cross-sector cluster · X"):
    return {"signature": sig, "score": score, "name_en": name, "name_zh": name,
            "n": 7, "score_label": ne._score_label(score),
            "recommended": [{"ticker": "AAA"}, {"ticker": "BBB"}]}


def test_emergence_alert_seed_then_fire_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    # seed run: no events, state persisted, alerts file empty
    em1 = _emergence([_nv("sig0001")])
    assert ea.rebuild(em1) == []
    assert (tmp_path / "emergence" / "state.json").exists()
    assert ea.load_events() == []

    # next run: a NEW forming narrative above the bar → exactly one event
    em2 = _emergence([_nv("sig0001"), _nv("sig0002")], as_of="2026-06-19")
    fired = ea.rebuild(em2)
    assert len(fired) == 1 and fired[0]["type"] == "narrative_forming"
    assert fired[0]["asset"] == "sig0002" and fired[0]["anchor"] == "#ne-sig0002"

    # idempotent re-run → no dup (keep-first by id)
    assert ea.rebuild(em2) == []
    assert len(ea.load_events()) == 1


def test_emergence_alert_skips_below_bar(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    assert ea.rebuild(_emergence([_nv("seed")])) == []          # seed
    # a faint narrative (below ALERT_MIN) must NOT fire even though it is new
    weak = _emergence([_nv("seed"), _nv("faint", score=ea.ALERT_MIN - 10)], as_of="2026-06-19")
    assert ea.rebuild(weak) == []
    assert ea.load_events() == []


# ------------------------------------------- AI-scout watch display register (#3821)
# The scout's emerging_watch is LLM prose printed VERBATIM by the Forming Narratives
# panel, so it is a user-cycle surface: the falsifier register never appears there
# (operator ruling 2026-07-27).  The CONDITION must survive the rewrite word-for-word.
_COND = "if it loses eligibility or falls below rank 3 within 15 days."


def test_watch_register_rewrites_kill_label_and_keeps_the_condition():
    out = ne._watch_register("Tech may challenge Miners. Kill criterion: " + _COND)
    assert out == "Tech may challenge Miners. Watching for: " + _COND
    assert "Kill" not in out and "kill" not in out


def test_watch_register_covers_label_variants():
    for lab in ("Kill criterion:", "kill criterion :", "Kill-criterion:", "KILL CRITERIA:",
                "Kill:", "kill："):
        out = ne._watch_register("Watch X. " + lab + " " + _COND)
        assert out == "Watch X. Watching for: " + _COND, lab
    # bare noun phrase (no colon) de-registers without inventing a label
    assert ne._watch_register("Its kill criterion is tight.") == \
        "Its watch condition is tight."


def test_watch_register_is_idempotent_and_leaves_clean_text_alone():
    clean = "Tech may challenge Miners. Watching for: " + _COND
    assert ne._watch_register(clean) == clean
    assert ne._watch_register(ne._watch_register(clean)) == clean
    # a word that merely CONTAINS "kill" is untouched
    assert ne._watch_register("Overkill: not a label.") == "Overkill: not a label."


def test_ai_watch_de_registers_a_stale_brief(tmp_path):
    """Old-vintage ai_desk_<region>.json (the gated desk lane re-runs on its own cadence)
    must not leak the old register through the panel payload."""
    alloc = tmp_path / "site" / "allocationdata"
    alloc.mkdir(parents=True)
    (alloc / "ai_desk_hk.json").write_text(
        '{"emerging_watch": "Semis may take leadership. Kill criterion: ' + _COND + '",'
        ' "confidence": "low", "state_asof": "2026-08-01"}', encoding="utf-8")
    w = ne._ai_watch(tmp_path, "hk")
    assert w is not None
    assert w["text"] == "Semis may take leadership. Watching for: " + _COND
    assert w["confidence"] == "low"
