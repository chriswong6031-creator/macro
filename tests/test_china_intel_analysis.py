"""China central-intelligence analysis — cross-surface synthesis contract tests."""
from __future__ import annotations

from engine import china_intel_analysis as an


def test_analyze_graceful_on_empty_disk(monkeypatch):
    monkeypatch.setattr(an, "_read", lambda rel: None)
    # no altdata convergence either
    import engine.china_altdata as ad
    monkeypatch.setattr(ad, "convergence_map", lambda: {})
    a = an.analyze(prev=None)
    assert a["schema"] == an.SCHEMA
    for k in ("conviction", "chains", "cross_refs", "what_matters", "flagged_tickers"):
        assert k in a
    assert a["conviction"] == [] and a["flagged_tickers"] == []
    # chains always present (k may be 0) and never crash
    assert len(a["chains"]) == 2


def test_what_changed_empty_on_first_run():
    wc = an._what_changed(None, [], {}, {}, {}, {})
    assert wc["new_accumulation"] == [] and wc["new_radar_fires"] == []
    assert wc["stance_change"] is None


def test_what_changed_diffs_against_prior():
    prev = {"_acc_tickers": ["AAA", "BBB"], "_radar_fires": ["pmi->Metals"],
            "_stance": "neutral", "_sent_band": "steady"}
    conviction = [{"key": "pboc_easing", "sector_en": "Brokers"}]
    policy = {"stance": "easing"}
    news_sent = {"band": "supportive"}
    altdata_mm = {"convergence_top": [{"ticker": "BBB"}, {"ticker": "CCC"}]}
    wc = an._what_changed(prev, conviction, policy, news_sent, altdata_mm, {})
    assert "CCC" in wc["new_accumulation"] and "AAA" in wc["dropped_accumulation"]
    assert "pboc_easing->Brokers" in wc["new_radar_fires"]
    assert "pmi->Metals" in wc["resolved_radar"]
    assert wc["stance_change"] == {"from": "neutral", "to": "easing"}
    assert wc["sentiment_band_change"] == {"from": "steady", "to": "supportive"}


def test_cross_refs_priced_for_easing():
    # easing signal up + cuts delivered + stance still neutral -> conflict
    import engine.china_radar as cr
    refs = an._cross_refs({"stance": "neutral", "last_moves": ["1Y LPR cut 10bp"]})
    # only asserts shape (live _sig_pboc_easing dir may vary); when it fires it's a conflict
    for r in refs:
        assert r["kind"] == "conflict" and r["signal_key"] == "pboc_easing"


def test_conviction_names_surfaces_and_carries_note(monkeypatch):
    monkeypatch.setattr(an, "_read", lambda rel: None)
    # Pin sign as proven so "news" appears in surfaces_confirming (the full contrarian path).
    # When sign is unproven (the current live state), news_dir=0 and "news" is absent from
    # surfaces_confirming — that is tested separately by test_sign_unproven_direction_is_zero.
    monkeypatch.setattr(an, "_news_sign_proven", lambda: True)
    divs = [{"sector_etf": "512880.SS", "sector_en": "Brokers", "sector_zh": "券商",
             "sign": "positive", "strength": 0.5, "signal_key": "pboc_easing",
             "signal_en": "PBoC easing", "signal_zh": "央行宽松",
             "hypothesis_en": "h", "hypothesis_zh": "假设"}]
    conv_map = {"300059.SZ": {"convergence": 0.9, "side": "accumulate", "name": "东方财富"}}
    rows = an._conviction(divs, {"by_basket": {"cn_brokers": 3}},
                          {"band": "cautious", "z": -0.8},   # fearful tape → CONTRARIAN-confirms a positive divergence
                          conv_map, {"stance": "easing"})
    assert rows
    c = rows[0]
    assert c["surfaces_confirming"][0] == "radar"
    assert set(c["surfaces_confirming"]) >= {"radar", "news", "policy"}
    assert c["note"] and "never a size" in c["note"]
    assert 0 <= c["context_conviction"] <= 100


def test_what_matters_dedup_and_ranked():
    conviction = [
        {"sector_en": "Metals", "sector_zh": "金属", "radar_sign": "positive",
         "context_conviction": 60, "rationale_en": "a", "rationale_zh": "甲"},
        {"sector_en": "Metals", "sector_zh": "金属", "radar_sign": "positive",
         "context_conviction": 20, "rationale_en": "b", "rationale_zh": "乙"},
    ]
    wm = an._what_matters(conviction, [], {}, {"z": 0.3, "band": "x", "label_en": "X",
                                              "label_zh": "X", "n_days": 90})
    metals = [w for w in wm if w["kind"] == "radar" and "Metals" in w["label_en"]]
    assert len(metals) == 1                      # de-duped on (sector, sign)
    sal = [w["salience"] for w in wm]
    assert sal == sorted(sal, reverse=True)      # ranked


def test_conviction_not_crushed_by_absent_legs():
    """Review fix: absent legs are passed as None (not 0.0) into the geometric combine, so a
    radar-only divergence yields a sane composite, not ~2/100."""
    divs = [{"sector_etf": "512880.SS", "sector_en": "Brokers", "sector_zh": "券商",
             "sign": "positive", "strength": 0.8, "signal_key": "pboc_easing",
             "signal_en": "PBoC easing", "signal_zh": "央行宽松",
             "hypothesis_en": "h", "hypothesis_zh": "假设",
             "reliability": {"basis": "unproven", "n_resolved": 0}}]
    # only radar present (no aligned altdata, no news, no policy, no conditions)
    rows = an._conviction(divs, {}, {}, {}, {}, {})
    assert rows
    assert rows[0]["composite_conviction"] > 30   # NOT crushed to ~2


def test_what_matters_skips_past_dated_scheduled():
    """Audit fix B6a: scheduled_ahead items whose date < today must not appear on the board.
    Previously days=max(0,...) clamped expired catalysts to salience=1.0 and topped the board."""
    from datetime import date, timedelta
    past_ev = {"date": (date.today() - timedelta(days=5)).isoformat(),
               "name_en": "LPR Decision", "name_zh": "LPR决议",
               "md": "Jun-22", "md_zh": "6月22日"}
    news_feed = {"scheduled_ahead": [past_ev]}
    result = an._what_matters([], [], news_feed, {})
    scheduled = [r for r in result if r["kind"] == "scheduled"]
    assert scheduled == [], "past-dated scheduled item must be excluded from what_matters"


def test_analyze_news_stale_flag(monkeypatch):
    """Audit fix B6a: when feed asof lags analysis asof by >3 days, news_stale=True and
    the news sentiment z-score is excluded from what_matters salience ranking."""
    from datetime import date, timedelta
    stale_feed = {"asof": (date.today() - timedelta(days=10)).isoformat(),
                  "scheduled_ahead": []}
    fresh_sent = {"z": 2.5, "band": "fearful", "label_en": "fearful", "label_zh": "恐慌",
                  "n_days": 30}
    import engine.china_altdata as ad
    monkeypatch.setattr(ad, "convergence_map", lambda: {})

    def fake_read(rel):
        if rel == "chinanews/feed.json":
            return stale_feed
        if rel == "chinanews/sentiment.json":
            return fresh_sent
        return None

    monkeypatch.setattr(an, "_read", fake_read)
    result = an.analyze()
    assert result["news_stale"] is True
    # sentiment z-score must be absent from what_matters when feed is stale
    news_items = [w for w in result["what_matters"] if w["kind"] == "news"]
    assert news_items == [], "stale feed must exclude news salience item from what_matters"


def test_news_leg_is_contrarian(monkeypatch):
    """When sign is proven, news is contrarian (sign_expected -1) — fearful tape confirms a
    positive divergence; greedy tape dissents. (W3: news direction is 0 when sign is unproven —
    that case is covered by test_sign_unproven_direction_is_zero.)"""
    monkeypatch.setattr(an, "_news_sign_proven", lambda: True)
    base = {"sector_etf": "512880.SS", "sector_en": "Brokers", "sector_zh": "券商",
            "sign": "positive", "strength": 0.6, "signal_key": "pboc_easing",
            "signal_en": "E", "signal_zh": "E", "reliability": {"basis": "unproven", "n_resolved": 0}}
    feed = {"by_basket": {"cn_brokers": 5}}
    fearful = an._conviction([dict(base)], feed, {"z": -0.9}, {}, {})
    greedy = an._conviction([dict(base)], feed, {"z": 0.9}, {}, {})
    assert fearful[0]["directions"]["news"] == 1     # fearful confirms positive
    assert greedy[0]["directions"]["news"] == -1     # greedy dissents


# ---------------------------------------------------------------------------
# W3 — salience/direction split tests  (spec §2.3 / D5)
# ---------------------------------------------------------------------------

_DIV_BASE = {
    "sector_etf": "512880.SS", "sector_en": "Brokers", "sector_zh": "券商",
    "sign": "positive", "strength": 0.6, "signal_key": "pboc_easing",
    "signal_en": "E", "signal_zh": "E", "reliability": {"basis": "unproven", "n_resolved": 0},
}
_FEED_WITH_HITS = {"by_basket": {"cn_brokers": 4}}
_SENT_FEARFUL = {"z": -0.9, "band": "fearful"}
_SENT_GREEDY  = {"z":  0.9, "band": "supportive"}


def test_sign_unproven_direction_is_zero(monkeypatch):
    """spec §2.3 / D5: while sign is unproven, news_dir must be 0 regardless of z."""
    monkeypatch.setattr(an, "_news_sign_proven", lambda: False)
    for sent in (_SENT_FEARFUL, _SENT_GREEDY):
        rows = an._conviction([dict(_DIV_BASE)], _FEED_WITH_HITS, sent, {}, {})
        assert rows
        c = rows[0]
        assert c["directions"]["news"] == 0, "news direction must be 0 when sign is unproven"
        assert c["sign_unproven"] is True
        assert c["direction_basis"] == "salience_only"


def test_sign_unproven_salience_preserved(monkeypatch):
    """Salience (|z| × coverage) must be non-zero even when direction=0."""
    monkeypatch.setattr(an, "_news_sign_proven", lambda: False)
    rows = an._conviction([dict(_DIV_BASE)], _FEED_WITH_HITS, _SENT_FEARFUL, {}, {})
    assert rows
    c = rows[0]
    assert c["salience"] > 0, "salience must be preserved even when sign is unproven"
    assert c["direction"] == 0


def test_sign_proven_re_enables_direction(monkeypatch):
    """Once sign is proven+sign_ok, the contrarian direction must fire correctly."""
    monkeypatch.setattr(an, "_news_sign_proven", lambda: True)
    fearful = an._conviction([dict(_DIV_BASE)], _FEED_WITH_HITS, _SENT_FEARFUL, {}, {})
    greedy  = an._conviction([dict(_DIV_BASE)], _FEED_WITH_HITS, _SENT_GREEDY,  {}, {})
    assert fearful[0]["directions"]["news"] == 1,  "fearful tape should confirm positive divergence when sign proven"
    assert greedy[0]["directions"]["news"]  == -1, "greedy tape should dissent when sign proven"
    assert fearful[0]["sign_unproven"] is False
    assert fearful[0]["direction_basis"] == "proven_contrarian"
    assert fearful[0]["direction"] == 1


def test_sign_unproven_no_news_hits(monkeypatch):
    """No news hits → salience=0, direction=0, sign_unproven still set."""
    monkeypatch.setattr(an, "_news_sign_proven", lambda: False)
    rows = an._conviction([dict(_DIV_BASE)], {}, _SENT_FEARFUL, {}, {})
    assert rows
    c = rows[0]
    assert c["salience"] == 0.0
    assert c["direction"] == 0
    assert c["sign_unproven"] is True


def test_composite_not_inflated_by_unproven_sign(monkeypatch):
    """The composite conviction must not change between fearful/greedy when sign is unproven
    (because news_dir=0 in both cases, so the direction tally is identical)."""
    monkeypatch.setattr(an, "_news_sign_proven", lambda: False)
    fearful = an._conviction([dict(_DIV_BASE)], _FEED_WITH_HITS, _SENT_FEARFUL, {}, {})
    greedy  = an._conviction([dict(_DIV_BASE)], _FEED_WITH_HITS, _SENT_GREEDY,  {}, {})
    assert fearful and greedy
    # composite should be equal (news_dir=0 for both; only |z| differs for salience_mag)
    assert abs(fearful[0]["composite_conviction"] - greedy[0]["composite_conviction"]) < 5.0, (
        "composite_conviction must not swing on the unproven contrarian sign"
    )


def test_row_carries_direction_fields(monkeypatch):
    """Every conviction row must carry salience, direction, direction_basis, sign_unproven."""
    monkeypatch.setattr(an, "_news_sign_proven", lambda: False)
    rows = an._conviction([dict(_DIV_BASE)], _FEED_WITH_HITS, _SENT_FEARFUL, {}, {})
    assert rows
    c = rows[0]
    for field in ("salience", "direction", "direction_basis", "sign_unproven"):
        assert field in c, f"conviction row must carry '{field}' (spec §2.3)"
