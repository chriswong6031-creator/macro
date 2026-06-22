"""Contract tests for engine/stock_view.build_view + the stock_score view-facing gates."""
from __future__ import annotations

from engine import stock_view as sv
from engine import stock_score as ss


# ---------------------------------------------------------------------------
# fixtures — minimal normalized recs run through the real conviction engine
# ---------------------------------------------------------------------------
def _rec(market, **over):
    base = {"ticker": "T", "name": "Test", "alpha": 1.4,
            "ladder": {"state": "RALLY ON", "label": "Uptrend",
                       "entry": {"tag": "HOLD", "urgency": "hold"}},
            "tech": {"above200": True, "pct_vs_200dma": 8.0, "rsi14": 55.0}}
    base.update(over)
    return base


def _profiled(market, **over):
    rec = _rec(market, **over)
    rec["conviction"] = ss.conviction_profile(rec, market)
    return rec


# ---------------------------------------------------------------------------
def test_build_view_shape():
    rec = _profiled("US")
    v = sv.build_view(rec, "US")
    assert v["schema"] == sv.SCHEMA
    for k in ("decision", "fingerprint", "falsifiers", "evidence", "country_slot"):
        assert k in v
    d = v["decision"]
    assert d["headline"] and d["headline_zh"]
    assert d["state"] in ("ok", "conflict", "neutral")
    assert len(v["fingerprint"]["axes"]) == 4
    # selection axis is labelled by the firing leg, never a hardcoded market string
    assert v["fingerprint"]["axes"][0]["key"] == "selection"


def test_legacy_boolean_fragility_does_not_crash():
    """Older/build-specific records may mark fragility as a bool; the shared view
    renderer must coerce it instead of assuming the richer crowding payload."""
    rec = _profiled("CN", rev_z=1.2, fragility=True)
    v = sv.build_view(rec, "CN")
    assert any(f["en"] == "Crowded & fragile" for f in v["falsifiers"])


def test_every_emitted_verdict_has_a_gloss():
    """The gloss can never become a 5th drifting headline: it must be a pure lookup on
    the verdict enum. Build the full verdict universe and assert coverage."""
    seen = set()
    # sweep selection/entry/quality/cycle/accounting combinations across markets
    states = ["RALLY ON", "DECLINE", "TOP WATCH", "BOTTOM WATCH", "FRESH BUY"]
    for market in ss.MARKETS:
        for st in states:
            for a in (-1.5, -0.3, 0.5, 1.6):
                for tag, urg in (("HOLD", "hold"), ("BUY NOW", "now"),
                                 ("AVOID", "avoid"), ("DON'T CHASE", "caution")):
                    for acct in (None, "watch", "warn"):   # accounting flag changes the verb
                        rec = _rec(market, alpha=a,
                                   ladder={"state": st, "label": st,
                                           "entry": {"tag": tag, "urgency": urg}})
                        if acct:
                            rec["accounting"] = {"verdict": acct}
                        if market in ("CN",):
                            rec["rev_z"] = a
                        if market in ("HK",):
                            rec["rs_z"] = a
                        prof = ss.conviction_profile(rec, market)
                        seen.add(prof["verdict"])
    missing = [v for v in seen if v not in sv._VERDICT_GLOSS]
    assert not missing, f"verdicts with no gloss: {missing}"


def test_coherence_invariant_constructive_band_low_size_is_conflict():
    """A constructive/high band sized below a quarter must surface as a conflict — never
    a clean 'Constructive · 0%' headline (the C6 incoherence)."""
    # a strong selection name in a downtrend: high composite, blocked entry, size 0
    rec = _profiled("US", alpha=2.5,
                    ladder={"state": "DECLINE", "label": "Downtrend",
                            "entry": {"tag": "AVOID", "urgency": "avoid"}})
    v = sv.build_view(rec, "US")
    d = v["decision"]
    assert d["size"].get("pct") == 0
    assert d["state"] == "conflict"
    assert d["conflict_pillars"]            # names the fighting pillar(s)


def test_dont_chase_tag_is_capped():
    """Every entry tag cycles.py emits resolves to a finite size cap, or is an
    intentionally-uncapped/blocked tag. DON'T CHASE was the latent leak."""
    emitted = {"BUY NOW", "HALF SIZE", "BUY SOON", "WATCH", "WAIT", "HOLD",
               "TAKE PROFITS", "SELL / REDUCE", "AVOID",
               "UNCONFIRMED — HIGH RISK", "DON'T CHASE"}
    uncapped_ok = {"BUY NOW", "HOLD", "SELL / REDUCE", "AVOID"}  # full / blocked-to-0
    for tag in emitted:
        assert tag in ss._ENTRY_SIZE_CAP or tag in uncapped_ok, f"{tag} has no size cap"
    assert ss._ENTRY_SIZE_CAP["DON'T CHASE"] == 25


def test_close_only_fallback_does_not_crash():
    """A record with no conviction block (close-only markets) still yields a headline
    off the cycle/ladder spine."""
    rec = {"ladder": {"state": "FRESH BUY", "label": "Buy zone",
                      "summary_line": "Confirmed cycle low",
                      "entry": {"tag": "BUY NOW", "tag_zh": "立即买入", "urgency": "now"}}}
    v = sv.build_view(rec, "INTL")
    assert v["decision"]["headline"]
    assert v["fingerprint"]["axes"] == []
    assert v["evidence"] == {}


def test_country_slot_cards_activate_on_fields():
    rec = _profiled("CA", factor_beta={"oil": 0.8, "gold": -0.1, "cad": 0.3,
                                       "primary_label": "Oil driven", "r2": 0.4})
    cards = sv.build_view(rec, "CA")["country_slot"]["cards"]
    assert any(c["kind"] == "commodity_beta" for c in cards)

    rec = _profiled("HK", rs_z=1.0,
                    global_beta={"beta": 1.3, "role": "amplifier"},
                    ah_premium={"premium_pct": 22.0, "chg_1y": 4.0})
    cards = sv.build_view(rec, "HK")["country_slot"]["cards"]
    kinds = {c["kind"] for c in cards}
    assert {"global_beta", "ah_premium"} <= kinds
    # A/H rising premium row carries the down-color inversion (data, not template)
    ah = next(c for c in cards if c["kind"] == "ah_premium")
    chg_row = next(r for r in ah["rows"] if r.get("color"))
    assert chg_row["color"] == "down"


def test_us_country_slot_is_empty():
    """US has no country-specific cards — its richness is the evidence lanes."""
    assert sv.build_view(_profiled("US"), "US")["country_slot"]["cards"] == []


def test_hk_is_never_a_buy_verb():
    """HK semantic inversion preserved through the view: never a buy headline."""
    rec = _profiled("HK", rs_z=2.0, hk_edge_lead="bnrs")
    head = sv.build_view(rec, "HK")["decision"]["headline"].lower()
    assert "buy" not in head


def test_vol_squeeze_evidence():
    """The vol-squeeze timing confirmer surfaces as one evidence read, present-gated."""
    rec = _profiled("US")
    rec["vol_squeeze"] = {"state": "COILED", "days_compressed": 14, "coiled": True}
    sq = sv.build_view(rec, "US")["evidence"].get("squeeze")
    assert sq and "14d" in sq["value"] and sq["tone"] == "warn"
    # NONE / absent → no chip
    rec["vol_squeeze"] = {"state": "NONE"}
    assert "squeeze" not in sv.build_view(rec, "US")["evidence"]
    # an unconfirmed breakout is flagged as such
    rec["vol_squeeze"] = {"state": "FIRED_UP", "volume_confirmed": False}
    assert "unconfirmed" in sv.build_view(rec, "US")["evidence"]["squeeze"]["value"]


def test_cn_valuation_tone_is_neutral():
    """Cheapness is not a validated buy in CN — valuation never renders 'good'/green."""
    rec = _profiled("CN", rev_z=0.5, valuation={"value_z": 1.5})
    ev = sv.build_view(rec, "CN")["evidence"].get("valuation")
    if ev:
        assert ev["tone"] == "neutral"
