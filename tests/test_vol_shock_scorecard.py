"""Tests for engine.vol_shock_scorecard — the forward vol-shock risk gauge.

Covers: full-input fusion, the points-sum-to-score invariant, graceful
renormalization when factors drop out, all-missing -> hidden card, the
never-raises contract on malformed input, the capped/young factor rules, and the
forward-outcome log roundtrip (append -> resolve -> track_record).
"""
from __future__ import annotations

import json

import pytest

from engine import vol_shock_scorecard as vss


def _full_latest() -> dict:
    """A representative latest.json-shaped dict with every leading factor present."""
    return {
        "date": "2026-06-18",
        "market_gamma": {  # sibling S2's first-class field
            "regime": "short", "spot_vs_flip_pct": -0.5,
            "net_gex_bn": -2.0, "gamma_flip": 7461.0,
            "asof": "2026-06-18",           # engine.market_gamma.view always stamps this
        },
        "cross_asset": {"asof": "2026-06-18", "absorption_pctile_5y": 0.94},
        "dislocation": {"asof": "2026-06-18", "inputs": {"vix": 16.4, "vix_term": 0.98}},
        "turning_point": {"present": False, "state": "normal",
                          "drivers": {"one_factor": True}},
        "conditions": {
            "complacency": {"state": "watch", "warning": True, "breadth_div": True},
            "drawdown_risk": {"score": 13.8, "band": "low"},
            "risk_appetite": {"vrp_pctile": 0.13, "skew_pctile": 0.50,
                              "vrp_state": "normal", "vix_term": 0.98},
        },
    }


def _vs_sentiment() -> dict:
    return {
        "vol_regime": {"term_ratio": 0.98, "vrp_state": "normal", "skew": 146.7},
        "put_call": {"equity_pct_in_hist": 0.1, "n_obs": 200, "young": False},
    }


# --------------------------------------------------------------------------- #
# Full-input fusion + invariants
# --------------------------------------------------------------------------- #
def test_full_input_score():
    # Audit #29: dealer_gamma is DISPLAY-ONLY (weight 0) while data/gex/gate.json is closed, so
    # only 8 of 9 factors are AVAILABLE (score-bearing) by default. The dealer_gamma row is still
    # present + computed, just gated out of the weighted mean.
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    assert snap is not None
    assert snap["score"] is not None
    assert 0 <= snap["score"] <= 100
    assert snap["band"] in ("low", "elevated", "high", "extreme")
    assert snap["n_available"] == 8          # 9 factors, dealer_gamma gated out (assumption sign)
    assert snap["why"] and snap["why_zh"]
    # every active factor carries the display contract
    for f in snap["factors"]:
        assert set(("key", "label", "label_zh", "value", "points", "weight",
                    "available", "sub", "color", "note")) <= set(f)
    # the dealer_gamma row is present, gated out, and carries an assumption passport
    dg = next(f for f in snap["factors"] if f["key"] == "dealer_gamma")
    assert dg["gated_out"] is True and dg["weight"] == 0.0 and dg["available"] is False
    assert dg["passport"]["basis"] == "assumption"
    assert dg["passport"]["verdict"] == "display-only"


def test_full_input_score_with_gate_open(monkeypatch):
    # With the gate OPEN the dealer_gamma factor rejoins the weighted mean (all 9 available).
    monkeypatch.setattr(vss, "_gex_gate_scored", lambda: True)
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    assert snap["n_available"] == 9
    dg = next(f for f in snap["factors"] if f["key"] == "dealer_gamma")
    assert dg["gated_out"] is False and dg["weight"] > 0 and dg["available"] is True
    assert dg["passport"]["verdict"] == "scored"


def test_points_sum_to_score():
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    total = sum(f["points"] for f in snap["factors"] if f["available"] and f["points"])
    # points are rounded to 1dp; the sum reconstructs the headline within rounding
    assert abs(total - snap["score"]) <= 0.5


def test_dealer_gamma_subscore_computed_even_when_gated_out():
    """The dealer_gamma SUB-score is still computed for display (short-gamma near the flip reads
    high) even though it is gated out of the weighted mean."""
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    dg = next(f for f in snap["factors"] if f["key"] == "dealer_gamma")
    assert dg["gated_out"] is True           # not scored while gate closed
    assert dg["sub"] >= 75                    # short gamma + near flip still shown


def test_short_gamma_raises_vs_long_gamma():
    base = _full_latest()
    long_g = {**base, "market_gamma": {"regime": "long", "spot_vs_flip_pct": 5.0,
                                       "net_gex_bn": 5.0, "gamma_flip": 7000.0}}
    s_short = vss.snapshot(base, vol_sentiment=_vs_sentiment())
    s_long = vss.snapshot(long_g, vol_sentiment=_vs_sentiment())
    dg_short = next(f for f in s_short["factors"] if f["key"] == "dealer_gamma")["sub"]
    dg_long = next(f for f in s_long["factors"] if f["key"] == "dealer_gamma")["sub"]
    assert dg_short > dg_long


# --------------------------------------------------------------------------- #
# Dealer-gamma READ PROVENANCE — which tier answered, and when it was stamped.
#
# _resolve_gex has a 3-tier fallback (injected -> latest['market_gamma'] ->
# site/gex/SPX.json). Tier 3 is a PREVIOUS build's file and can be arbitrarily old, but the
# normalized dict used to return only {regime, gamma_flip, net_gex_bn, spot_vs_flip_pct} —
# so the promised "staleness shows in asof" had no data path and a month-old board read
# exactly like a live contract. These pin the carry-through + the plain-word disclosure.
# --------------------------------------------------------------------------- #
def _write_board(root, key: str, summary: dict, asof: str | None = "2026-06-18") -> None:
    """A site/gex/<KEY>.json shaped like the REAL board: ENGINE field naming in `summary`
    (gamma_regime / dist_to_flip_pct) and the as-of under `meta` — NOT `summary.asof`,
    which is the shape the old code looked for and the board never writes."""
    p = root / "gex" / f"{key}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    doc: dict = {"summary": summary}
    if asof is not None:
        doc["meta"] = {"key": key, "asof": asof}
    p.write_text(json.dumps(doc))


def test_contract_tier_carries_its_asof_and_source():
    gx = vss._resolve_gex(_full_latest(), None)
    assert gx["source"] == "contract"
    assert gx["asof"] == "2026-06-18"


def test_injected_tier_carries_its_asof_and_source():
    gx = vss._resolve_gex({"date": "2026-06-18"},
                          {"regime": "long", "spot_vs_flip_pct": 2.0, "asof": "2026-06-17"})
    assert gx["source"] == "injected"
    assert gx["asof"] == "2026-06-17"


def test_site_board_tier_carries_asof_from_meta_not_summary(monkeypatch, tmp_path):
    """The tier-3 fallback's date lives in `meta`, so reading only the top level or
    `summary` (the pre-fix shape) leaves it None on every real artifact."""
    _write_board(tmp_path, "SPX", {"gamma_regime": "short", "dist_to_flip_pct": -1.7,
                                   "net_gex_bn": -55.0, "gamma_flip": 7442.0},
                 asof="2026-06-11")
    monkeypatch.setattr(vss, "_site_dir", lambda: tmp_path)
    gx = vss._resolve_gex({"market_gamma": None}, None)      # the null-contract incident shape
    assert gx["regime"] == "short"                            # fallback still answers
    assert gx["source"] == "site_board"                       # ...and says WHICH tier did
    assert gx["asof"] == "2026-06-11"                         # ...and WHEN it was stamped


def test_stale_site_board_is_disclosed_in_plain_words(monkeypatch, tmp_path):
    """A site board that is WEEKS old — not "one build stale" — must say so on the row, in
    plain words, with the machine receipt alongside. This is the whole defect: an arbitrarily
    old fallback previously fed the factor indistinguishably from a live contract."""
    _write_board(tmp_path, "SPX", {"gamma_regime": "short", "dist_to_flip_pct": -1.7,
                                   "net_gex_bn": -55.0, "gamma_flip": 7442.0},
                 asof="2026-05-19")                          # 30 days before the snapshot
    monkeypatch.setattr(vss, "_site_dir", lambda: tmp_path)
    latest = _full_latest()
    latest["market_gamma"] = None
    snap = vss.snapshot(latest, vol_sentiment=_vs_sentiment())

    assert snap["gex_source"] == "site_board"
    assert snap["gex_asof"] == "2026-05-19"
    assert snap["gex_age_days"] == 30

    dg = next(f for f in snap["factors"] if f["key"] == "dealer_gamma")
    assert dg["source"] == "site_board"
    assert dg["source_asof"] == "2026-05-19"
    assert dg["source_age_days"] == 30
    assert dg["passport"]["read"] == {"source": "site_board", "asof": "2026-05-19",
                                      "age_days": 30, "snapshot_asof": "2026-06-18"}
    # plain-word window statement on the row, both languages (DESIGN_DOCTRINE Law 2/5)
    assert "2026-05-19" in dg["note"] and "30 days before this update" in dg["note"]
    assert "2026-05-19" in dg["note_zh"] and "比本次更新早 30 天" in dg["note_zh"]
    # the base note is still translated — the suffix is appended AFTER the _NOTE_ZH lookup,
    # so an untranslatable composite can never silently drop ZH back to English
    assert "做市商持空头 Gamma" in dg["note_zh"]
    # calm statement, never an alarm
    for alarm in ("STALE", "stale", "WARNING", "⚠", "!"):
        assert alarm not in dg["note"], f"alarm vocabulary in a calm window statement: {alarm}"


def test_same_session_read_discloses_nothing_extra():
    """No gap, nothing to disclose — the row must not grow a noise clause when the read and
    the snapshot are the same session (word budgets are hard limits)."""
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    dg = next(f for f in snap["factors"] if f["key"] == "dealer_gamma")
    assert snap["gex_age_days"] == 0
    assert dg["note"] == "dealers short gamma — they amplify moves"
    assert "gamma read" not in dg["note"]


def test_read_from_a_later_session_than_the_snapshot_is_disclosed(monkeypatch, tmp_path):
    """The live 2026-07-29 shape: the board had already been rewritten for 07-30, so the
    fallback fused a LATER session's gamma into an earlier snapshot. A mixed-as-of read is
    just as undisclosed as an old one — say which way it leans."""
    _write_board(tmp_path, "SPX", {"gamma_regime": "short", "dist_to_flip_pct": -1.7},
                 asof="2026-06-19")
    monkeypatch.setattr(vss, "_site_dir", lambda: tmp_path)
    latest = _full_latest()
    latest["market_gamma"] = None
    snap = vss.snapshot(latest, vol_sentiment=_vs_sentiment())
    assert snap["gex_age_days"] == -1
    dg = next(f for f in snap["factors"] if f["key"] == "dealer_gamma")
    assert "1 day after this update" in dg["note"]
    assert "比本次更新晚 1 天" in dg["note_zh"]


def test_undated_read_says_its_age_is_unknown(monkeypatch, tmp_path):
    """An absent stamp is disclosed as absent rather than passing for fresh — a board with no
    `meta` is exactly the silent case this fix exists to close."""
    _write_board(tmp_path, "SPX", {"gamma_regime": "short", "dist_to_flip_pct": -1.7},
                 asof=None)
    monkeypatch.setattr(vss, "_site_dir", lambda: tmp_path)
    latest = _full_latest()
    latest["market_gamma"] = None
    snap = vss.snapshot(latest, vol_sentiment=_vs_sentiment())
    assert snap["gex_asof"] is None and snap["gex_age_days"] is None
    dg = next(f for f in snap["factors"] if f["key"] == "dealer_gamma")
    assert "no date" in dg["note"] and "age is unknown" in dg["note"]
    assert "没有日期" in dg["note_zh"]


def test_live_contract_is_not_shadowed_by_the_board(monkeypatch, tmp_path):
    """Tier 2 beats tier 3 and tier 3 is never even READ — the provenance fields must not
    turn the fallback into an unconditional disk hit."""
    _write_board(tmp_path, "SPX", {"gamma_regime": "long", "dist_to_flip_pct": 2.0},
                 asof="2026-05-19")
    monkeypatch.setattr(vss, "_site_dir", lambda: tmp_path)
    reads: list = []
    real_read_json = vss._read_json
    monkeypatch.setattr(vss, "_read_json",
                        lambda path: (reads.append(path), real_read_json(path))[1])
    gx = vss._resolve_gex(_full_latest(), None)
    assert gx["source"] == "contract" and gx["regime"] == "short"
    assert not reads, f"tier 3 must not be consulted when the contract is live: {reads}"


def test_products_disagree_reports_the_board_dates(monkeypatch, tmp_path):
    """The SPY-vs-SPX contradiction flag promises `spy_asof`/`spx_asof`; those read the same
    `meta` stamp, so before this fix both were permanently None on the real artifacts."""
    _write_board(tmp_path, "SPY", {"gamma_regime": "short"}, asof="2026-06-18")
    _write_board(tmp_path, "SPX", {"gamma_regime": "long"}, asof="2026-06-17")
    monkeypatch.setattr(vss, "_site_dir", lambda: tmp_path)
    p = vss._products_disagree()
    assert p["disagree"] is True
    assert p["spy_asof"] == "2026-06-18" and p["spx_asof"] == "2026-06-17"


def test_provenance_survives_a_malformed_board(monkeypatch, tmp_path):
    """Degrade-never-raise: a board whose as-of is junk still resolves, and the junk stamp is
    disclosed verbatim rather than dropped (a present-but-odd date is information)."""
    _write_board(tmp_path, "SPX", {"gamma_regime": "short", "dist_to_flip_pct": -1.7},
                 asof="not-a-date")
    monkeypatch.setattr(vss, "_site_dir", lambda: tmp_path)
    latest = _full_latest()
    latest["market_gamma"] = None
    snap = vss.snapshot(latest, vol_sentiment=_vs_sentiment())
    assert snap["gex_asof"] == "not-a-date"
    assert snap["gex_age_days"] is None
    dg = next(f for f in snap["factors"] if f["key"] == "dealer_gamma")
    assert "not-a-date" in dg["note"]


# --------------------------------------------------------------------------- #
# Graceful degradation / renormalization
# --------------------------------------------------------------------------- #
def test_missing_one_factor_renormalizes():
    latest = _full_latest()
    latest.pop("cross_asset")           # drop the heaviest-weighted leading factor
    snap = vss.snapshot(latest, vol_sentiment=_vs_sentiment())
    assert snap["score"] is not None
    conc = next(f for f in snap["factors"] if f["key"] == "concentration")
    assert conc["available"] is False
    assert conc["points"] is None
    # remaining points still reconstruct the (renormalized) headline
    total = sum(f["points"] for f in snap["factors"] if f["available"] and f["points"])
    assert abs(total - snap["score"]) <= 0.5


@pytest.mark.parametrize("drop", [
    "cross_asset", "market_gamma", "turning_point", "conditions",
])
def test_each_factor_drop_is_graceful(drop):
    latest = _full_latest()
    latest.pop(drop, None)
    snap = vss.snapshot(latest, vol_sentiment=_vs_sentiment())
    assert snap is not None
    # still a valid renormalized score as long as >=1 factor remains
    if snap["n_available"]:
        assert 0 <= snap["score"] <= 100


def test_all_missing_hides_card(monkeypatch):
    # disable the side-car disk fallbacks so "no factors" is truly hermetic
    monkeypatch.setattr(vss, "_site_dir", lambda: None)
    snap = vss.snapshot({"date": "2026-06-18"})   # no factor sub-trees at all
    assert snap is not None                        # contract shell still returned
    assert snap["score"] is None
    assert snap["band"] is None
    assert snap["n_available"] == 0


def test_empty_and_none_inputs():
    assert vss.snapshot(None) is None
    assert vss.snapshot({}) is None
    assert vss.snapshot([]) is None  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Factor-specific rules
# --------------------------------------------------------------------------- #
def test_put_call_young_downweighted():
    young = {"vol_regime": {"term_ratio": 0.9},
             "put_call": {"equity_pct_in_hist": 0.1, "n_obs": 10, "young": True}}
    snap = vss.snapshot(_full_latest(), vol_sentiment=young)
    pc = next(f for f in snap["factors"] if f["key"] == "put_call")
    base_w = vss.DEFAULTS["weights"]["put_call"]
    assert pc["weight"] < base_w        # effective weight reduced
    assert "young" in pc["note"]


def test_turning_point_capped():
    latest = _full_latest()
    latest["turning_point"] = {"present": True, "state": "fragile"}
    snap = vss.snapshot(latest, vol_sentiment=_vs_sentiment())
    tp = next(f for f in snap["factors"] if f["key"] == "turning_point")
    assert tp["sub"] <= vss.DEFAULTS["turning_point_cap"]


# --------------------------------------------------------------------------- #
# Never-raises contract on malformed input
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [
    {"date": "x", "cross_asset": "not-a-dict"},
    {"date": "x", "cross_asset": {"absorption_pctile_5y": "oops"}},
    {"date": "x", "conditions": {"risk_appetite": None, "complacency": []}},
    {"date": "x", "market_gamma": {"regime": 123, "spot_vs_flip_pct": "nan"}},
    {"date": "x", "turning_point": "broken", "dislocation": 5},
])
def test_never_raises_on_malformed(bad):
    # must not raise, must return a dict with the contract keys
    snap = vss.snapshot(bad)
    assert isinstance(snap, dict)
    assert "score" in snap and "factors" in snap


# --------------------------------------------------------------------------- #
# Forward-outcome log roundtrip
# --------------------------------------------------------------------------- #
def test_forward_log_roundtrip(tmp_path):
    p = tmp_path / "log.jsonl"
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    assert vss.append_log(snap, _full_latest(), path=p) is True
    assert vss.append_log(snap, _full_latest(), path=p) is False  # idempotent per date

    # forward path that triggers the VIX-jump HIT: anchor VIX 16.4 -> high 30 (>1.4x)
    dates = ["2026-06-18"] + [f"2026-06-{d}" for d in range(19, 30)]  # >= horizon ahead
    spy_closes = {d: 100.0 for d in dates}
    spy_closes["2026-06-25"] = 90.0           # -10% drawdown intraday window too
    vix_highs = {d: 16.0 for d in dates}
    vix_highs["2026-06-24"] = 30.0            # VIX jump 30/16.4 = 1.83x >= 1.4x
    n = vss.resolve(spy_closes, vix_highs, path=p)
    assert n == 1

    tr = vss.track_record(path=p)
    assert tr["n"] == 1
    assert tr["hit_rate"] == 1.0
    assert "by_band" in tr


def test_resolve_not_matured_is_skipped(tmp_path):
    p = tmp_path / "log.jsonl"
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    vss.append_log(snap, _full_latest(), path=p)
    # only 3 forward days available (< horizon 10) => not matured => unresolved
    spy_closes = {"2026-06-18": 100.0, "2026-06-19": 100.0,
                  "2026-06-20": 100.0, "2026-06-21": 100.0}
    assert vss.resolve(spy_closes, {}, path=p) == 0
    assert vss.track_record(path=p)["n"] == 0


# --------------------------------------------------------------------------- #
# Dealer-gamma input resolution — the _resolve_gex fallback CHAIN
# (injected gex -> latest['market_gamma'] -> site/gex/SPX.json summary). Every
# test above stubs _site_dir to None, so tier 3 was previously uncovered.
# --------------------------------------------------------------------------- #
def _write_site_spx(root, summary: dict) -> None:
    """Lay down a site/gex/SPX.json shaped like the engine board's own summary
    (ENGINE naming: gamma_regime / dist_to_flip_pct), under a fake site dir."""
    p = root / "gex" / "SPX.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"summary": summary}))


def test_resolve_gex_falls_back_to_site_spx_json_when_contract_null(monkeypatch, tmp_path):
    """Tier 3: with latest['market_gamma'] NULL, the scorecard keeps its dealer-gamma
    factor by reading the engine board's site/gex/SPX.json — and normalizes the ENGINE
    field names onto the contract's (gamma_regime -> regime, dist_to_flip_pct ->
    spot_vs_flip_pct).

    Incident 2026-06-24 -> 07-28: the cboe/gex producer emitted a NaN flip on every
    net-negative session, which nulled latest['market_gamma'] — and _resolve_gex did NOT
    go dark, it silently dropped to this site-JSON tier, so the factor switched from
    legacy-frame values to engine-board values with no signal. Since PR #4004 both tiers
    carry the SAME engine grid flip, so the switch no longer changes definitions; this
    test pins the fallback as a deliberate, tested contract rather than an accident."""
    _write_site_spx(tmp_path, {"gamma_regime": "short", "dist_to_flip_pct": -1.6,
                               "net_gex_bn": -55.0, "gamma_flip": 7435.0})
    monkeypatch.setattr(vss, "_site_dir", lambda: tmp_path)
    g = vss._resolve_gex({"market_gamma": None}, None)   # the incident shape
    assert g["regime"] == "short"                         # aliased from gamma_regime
    assert g["spot_vs_flip_pct"] == pytest.approx(-1.6)   # aliased from dist_to_flip_pct
    assert g["gamma_flip"] == pytest.approx(7435.0)
    assert g["net_gex_bn"] == pytest.approx(-55.0)


def test_resolve_gex_prefers_live_contract_over_site_json(monkeypatch, tmp_path):
    """Tier 2 beats tier 3: a LIVE latest['market_gamma'] wins and the (one-build-stale)
    site JSON is never even read — so the fallback can't silently shadow a good contract."""
    _write_site_spx(tmp_path, {"gamma_regime": "long", "dist_to_flip_pct": 2.0,
                               "net_gex_bn": 12.0, "gamma_flip": 7100.0})
    monkeypatch.setattr(vss, "_site_dir", lambda: tmp_path)
    reads: list = []
    real_read_json = vss._read_json
    monkeypatch.setattr(vss, "_read_json",
                        lambda path: (reads.append(path), real_read_json(path))[1])
    g = vss._resolve_gex({"market_gamma": {"regime": "short", "spot_vs_flip_pct": -1.6,
                                           "net_gex_bn": -55.0, "gamma_flip": 7435.0}},
                         None)
    assert g["regime"] == "short"                          # contract, not the "long" JSON
    assert g["spot_vs_flip_pct"] == pytest.approx(-1.6)    # contract, not the +2.0 JSON
    assert g["gamma_flip"] == pytest.approx(7435.0)
    assert not reads, f"tier 3 must not be consulted when the contract is live: {reads}"
