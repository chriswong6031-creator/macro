"""Beyond-Quiver data-source expansion — hermetic tests for the new sources wired into the
two kernels: the Divergence Radar fuser (engine.theme_activity) and the alt-data convergence
kernel (engine.altdata_models). Every test injects synthetic frames so it never touches the
network or the on-disk parquet tables.

Sources covered:
  * Step 0  theme_event source kind (pre-aggregated per-basket counts)
  * Step 1  USAspending assistance (grants/loans) -> wide divergence leg + gov_grant channel
  * Step 2  SEC EDGAR 8-K material events        -> theme_event leg + material_8k channel
  * Step 3  Grants.gov FOAs                       -> theme_event leg (gated, degrades to empty)
  * Step 4  openFDA drug approvals                -> fda_approval / fda_label_expansion channels
  * Step 5  Hugging Face model downloads          -> hf_model_momentum channel
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import altdata_models as M
from engine import theme_activity as ta


def _payload(rels: dict[str, float]):
    """A minimal baskets payload: id -> 60d rel; members are 2 synthetic tickers each."""
    return {"baskets": [
        {"id": bid, "name": bid, "name_zh": bid, "category": "x",
         "members": [{"symbol": f"{bid.upper()}1"}, {"symbol": f"{bid.upper()}2"}],
         "perf": {"60d": {"rel": rel}}}
        for bid, rel in rels.items()]}


# ===================================================================== Step 0
def test_theme_event_metric_burst_vs_flat():
    """theme_event accel: a count burst reads positive; a flat count is silent-ish (~1x)."""
    frame = pd.DataFrame({"recent_count": [12, 1], "prior_count": [3, 1],
                          "n_members": [4, 1], "covered": ["A,B,C,D", "E"]},
                         index=["hot", "flat"])
    frame.index.name = "basket_id"
    src = {"name": "x", "kind": "theme_event", "min_prior": 1.0}
    hot = ta._theme_event_metric(src, "hot", frame=frame)
    flat = ta._theme_event_metric(src, "flat", frame=frame)
    assert hot["accel"] == 4.0 and hot["metric"] > 0 and hot["covered"] == ["A", "B", "C", "D"]
    assert flat["accel"] == 1.0 and abs(flat["metric"]) < 1e-9
    assert ta._theme_event_metric(src, "missing", frame=frame) is None


def test_theme_event_silent_when_both_zero():
    frame = pd.DataFrame({"recent_count": [0], "prior_count": [0]}, index=["q"])
    frame.index.name = "basket_id"
    src = {"name": "x", "kind": "theme_event"}
    assert ta._theme_event_metric(src, "q", frame=frame) is None  # no activity -> silent


def test_theme_event_fuses_into_radar_leg():
    """A theme_event source injected via sources_data must produce a z-leg and obs_dir."""
    ta.SOURCES.append({"name": "te_test", "kind": "theme_event", "group": "x", "series": "y",
                       "weight": 0.45, "label_en": "TE", "label_zh": "TE"})
    try:
        frame = pd.DataFrame({"recent_count": [20, 2], "prior_count": [4, 2]},
                             index=["hot", "cold"])
        frame.index.name = "basket_id"
        out = ta.compute_real_activity(_payload({"hot": -0.04, "cold": 0.01}),
                                       sources_data={"te_test": frame}, news=False)
        assert out["hot"]["obs_dir"] == 1 and out["hot"]["fused_obs_z"] > out["cold"]["fused_obs_z"]
    finally:
        ta.SOURCES.pop()


# ===================================================================== Step 1
def _wide(series: dict[str, list[float]], periods: int = 24):
    idx = pd.date_range(end="2026-05-01", periods=periods, freq="MS")
    return pd.DataFrame({k: pd.Series(v[-periods:], index=idx[-len(v[-periods:]):])
                         for k, v in series.items()}).reindex(idx)


def test_assistance_sequential_accel_lights_basket():
    """Grants use seasonal=False (sequential recent-vs-prior). A basket whose members'
    grant $ ramped recently must register; a flat one stays muted."""
    M_ = 1e6
    # 12 months flat-low then 6 months high for nuke; flat for housing
    ramp = [2 * M_] * 12 + [30 * M_] * 6
    flat = [3 * M_] * 18
    wide = _wide({"NUKE1": ramp, "NUKE2": ramp, "HOUSE1": flat, "HOUSE2": flat}, periods=18)
    src = {"name": "usaspending_assistance", "kind": "wide", "signed": False,
           "min_base": 5e6, "recent_months": 6, "seasonal": False}
    nuke = ta.source_accel(wide, ["NUKE1", "NUKE2"], signed=False, min_base=5e6,
                           recent_months=6, seasonal=False)
    house = ta.source_accel(wide, ["HOUSE1", "HOUSE2"], signed=False, min_base=5e6,
                            recent_months=6, seasonal=False)
    assert nuke is not None and nuke["accel"] > 3.0      # 30 vs 2 -> big accel
    assert house is not None and abs(house["accel"] - 1.0) < 0.01


def test_gov_grant_channel_fires_and_tiers():
    """gov_grant_accel outranks gov_grant; below the floor -> no channel."""
    signals = {"gov_grants": [
        {"ticker": "AAA", "total_usd": 80e6, "accel_x": 3.0},   # accel + above floor -> accel channel
        {"ticker": "BBB", "total_usd": 40e6, "accel_x": None},  # present, no accel -> plain channel
        {"ticker": "CCC", "total_usd": 1e6, "accel_x": 5.0},    # below floor -> nothing
    ]}
    recs = M.channel_records(signals)
    assert recs["AAA"]["channels"] == ["gov_grant_accel"]
    assert recs["BBB"]["channels"] == ["gov_grant"]
    assert "CCC" not in recs or not recs["CCC"]["channels"]
    # weight ordering: accel channel weighs more than plain presence
    assert M.CHANNEL_WEIGHTS["gov_grant_accel"] > M.CHANNEL_WEIGHTS["gov_grant"]


# ===================================================================== P3.3 handshake
def test_special_situations_handshake_lights_channels():
    """The Special-Situations desk cross-emit lights an activist_13d / special_situation
    channel so a confirmed event converges with the hard alt-data feeds on the same name."""
    signals = {"special_situations": [
        {"ticker": "AAA", "category": "Activist Campaigns", "activist": True, "filer": "Elliott"},
        {"ticker": "BBB", "category": "Going-Private", "activist": False, "detail": "Going-Private"},
    ]}
    recs = M.channel_records(signals)
    assert recs["AAA"]["channels"] == ["activist_13d"]
    assert "Elliott" in recs["AAA"]["channel_detail"]["activist_13d"]
    assert recs["BBB"]["channels"] == ["special_situation"]
    # the activist 13D handshake outweighs a generic special-situation
    assert M.CHANNEL_WEIGHTS["activist_13d"] > M.CHANNEL_WEIGHTS["special_situation"]


def test_special_situations_reader_drops_low_confidence(tmp_path, monkeypatch):
    """special_situations_signal() never propagates unverified (low-confidence) keyword guesses."""
    import json
    from lib import config
    from engine import altdata as A
    monkeypatch.setattr(config, "ROOT", tmp_path)
    d = tmp_path / "site" / "allocationdata"
    d.mkdir(parents=True)
    (d / "special_situations.json").write_text(json.dumps({"by_ticker": {
        "AAA": {"category": "Activist Campaigns", "confidence": "high", "activist_filer": "Elliott"},
        "BBB": {"category": "Acquisitions", "confidence": "low"},
    }}))
    out = {r["ticker"]: r for r in A.special_situations_signal()}
    assert "AAA" in out and out["AAA"]["activist"] is True and out["AAA"]["filer"] == "Elliott"
    assert "BBB" not in out                       # low confidence dropped


# ===================================================================== Step 2
def test_material_8k_channel_needs_a_cluster():
    """material_8k fires only on a cluster (>=2 material 8-Ks); a single one is not a signal."""
    signals = {"material_8k": [
        {"ticker": "AAA", "count": 3, "items": "1.01, 8.01"},
        {"ticker": "BBB", "count": 1, "items": "5.02"},
    ]}
    recs = M.channel_records(signals)
    assert recs["AAA"]["channels"] == ["material_8k"]
    assert recs["AAA"]["material_8k_30d"] == 3
    assert "BBB" not in recs or "material_8k" not in recs["BBB"]["channels"]


def test_edgar_8k_velocity_rollup():
    """The collector's per-basket velocity: counts material 8-Ks among members, recent vs prior,
    and stays silent for a basket with no member filings."""
    from collectors import edgar_8k
    events = pd.DataFrame([
        {"ticker": "LLY", "filing_date": "2026-06-10", "items": "8.01"},     # recent
        {"ticker": "LLY", "filing_date": "2026-06-01", "items": "1.01"},     # recent
        {"ticker": "NVO", "filing_date": "2026-05-20", "items": "8.01"},     # recent
        {"ticker": "LLY", "filing_date": "2026-03-20", "items": "1.01"},     # prior window (60-120d before 06-10)
        {"ticker": "DHI", "filing_date": "2026-06-05", "items": "5.02"},     # other basket
    ])
    mem = {
        "obesity_glp1": {"members": [{"ticker": "LLY"}, {"ticker": "NVO"}]},
        "housing": {"members": [{"ticker": "DHI"}, {"ticker": "LEN"}]},
        "empty": {"members": [{"ticker": "ZZZZ"}]},
    }
    vel = edgar_8k.Edgar8KAdapter()._velocity(events, mem)
    assert vel.loc["obesity_glp1", "recent_count"] == 3
    assert vel.loc["obesity_glp1", "prior_count"] == 1
    assert set(vel.loc["obesity_glp1", "covered"].split(",")) == {"LLY", "NVO"}
    assert "empty" not in vel.index  # no member activity -> not present


def test_item_filter_excludes_routine():
    """The material-item filter keeps 1.01/8.01/5.02 etc. and drops routine earnings/voting/exhibits."""
    from collectors import edgar_8k
    assert "1.01" in edgar_8k.MATERIAL_ITEMS and "8.01" in edgar_8k.MATERIAL_ITEMS
    assert "2.02" not in edgar_8k.MATERIAL_ITEMS  # earnings
    assert "9.01" not in edgar_8k.MATERIAL_ITEMS  # exhibits
    assert "5.07" not in edgar_8k.MATERIAL_ITEMS  # voting results


# ===================================================================== Step 3
def test_grants_gov_velocity_maps_cfda_to_baskets():
    """A FOA's CFDA listing maps to its theme(s); recent vs prior split by post_date."""
    from collectors import grants_gov
    cfda_map = {"81.121": ["nuclear_power"], "47.070": ["ai_software", "cybersecurity"]}
    opps = [
        {"opportunity_assistance_listings": [{"assistance_listing_number": "81.121"}],
         "summary": {"post_date": "2026-06-10"}},                       # recent -> nuclear
        {"opportunity_assistance_listings": [{"assistance_listing_number": "81.121"}],
         "summary": {"post_date": "2026-02-15"}},                       # prior  -> nuclear
        {"opportunity_assistance_listings": [{"assistance_listing_number": "47.070"}],
         "summary": {"post_date": "2026-06-01"}},                       # recent -> ai_software + cybersecurity
        {"opportunity_assistance_listings": [{"assistance_listing_number": "99.999"}],
         "summary": {"post_date": "2026-06-01"}},                       # unmapped -> ignored
    ]
    vel = grants_gov.velocity(opps, cfda_map, today="2026-06-20")
    assert vel.loc["nuclear_power", "recent_count"] == 1
    assert vel.loc["nuclear_power", "prior_count"] == 1
    assert vel.loc["ai_software", "recent_count"] == 1
    assert vel.loc["cybersecurity", "recent_count"] == 1
    assert "99.999" not in [s for idx in vel.index for s in [idx]]  # unmapped CFDA contributes nothing


def test_grants_gov_gated_without_key(monkeypatch):
    """No GRANTS_GOV_API_KEY -> adapter flags expected_failure and fetch raises (reported blocked)."""
    from collectors import grants_gov
    monkeypatch.delenv("GRANTS_GOV_API_KEY", raising=False)
    a = grants_gov.GrantsGovAdapter()
    assert a.expected_failure  # surfaced as 'blocked' by the runner
    import pytest
    with pytest.raises(RuntimeError):
        a.fetch()


def test_grants_foa_source_skipped_when_absent():
    """The fuser silently skips grants_foa when its parquet/injection is absent (graceful)."""
    out = ta.compute_real_activity(_payload({"nuclear_power": 0.0}), sources_data={}, news=False)
    # no sources injected -> no output, but crucially no crash on the wired grants_foa entry
    assert out == {} or all("grants_foa" not in [s["name"] for s in v["sources"]] for v in out.values())


# ===================================================================== Step 4
def test_openfda_classify():
    from collectors import openfda
    assert openfda._classify("ORIG", "AP", "TYPE 1 - NEW MOLECULAR ENTITY") == "approval"
    assert openfda._classify("SUPPL", "AP", "EFFICACY") == "label_expansion"
    assert openfda._classify("SUPPL", "AP", "LABELING") is None       # routine label change
    assert openfda._classify("ORIG", "TA", "TYPE 1") is None          # tentative approval, not AP


def test_openfda_parse_results_windows_and_maps():
    from collectors import openfda
    results = [{
        "application_number": "NDA217806", "sponsor_name": "LILLY",
        "products": [{"brand_name": "ZEPBOUND"}],
        "submissions": [
            {"submission_type": "ORIG", "submission_status": "AP",
             "submission_class_code": "TYPE 1", "submission_status_date": "20260115"},
            {"submission_type": "SUPPL", "submission_status": "AP",
             "submission_class_code": "EFFICACY", "submission_status_date": "20260301"},
            {"submission_type": "SUPPL", "submission_status": "AP",
             "submission_class_code": "LABELING", "submission_status_date": "20260310"},  # ignored
            {"submission_type": "ORIG", "submission_status": "AP",
             "submission_class_code": "TYPE 1", "submission_status_date": "20190101"},     # before since
        ],
    }]
    rows = openfda.parse_results(results, "LLY", "LILLY", since="20250101")
    kinds = sorted(r["kind"] for r in rows)
    assert kinds == ["approval", "label_expansion"]
    assert all(r["ticker"] == "LLY" and r["drug_name"] == "ZEPBOUND" for r in rows)


def test_fda_channels_fire():
    signals = {"fda": [
        {"ticker": "LLY", "kind": "approval", "drug": "ZEPBOUND"},
        {"ticker": "NVO", "kind": "label_expansion", "drug": "WEGOVY"},
    ]}
    recs = M.channel_records(signals)
    assert recs["LLY"]["channels"] == ["fda_approval"]
    assert recs["NVO"]["channels"] == ["fda_label_expansion"]
    # a new approval outranks a label expansion
    assert M.CHANNEL_WEIGHTS["fda_approval"] > M.CHANNEL_WEIGHTS["fda_label_expansion"]


# ===================================================================== Step 5
def test_hf_momentum_velocity(tmp_path, monkeypatch):
    """hf_momentum derives WoW velocity from >=2 snapshots and flags the above-median risers."""
    from lib import config
    from engine import altdata
    d = tmp_path / "huggingface"
    d.mkdir()
    snaps = pd.DataFrame([
        {"ticker": "META", "downloads_30d": 100.0, "n_models": 5, "snapshot_date": "2026-06-01"},
        {"ticker": "META", "downloads_30d": 150.0, "n_models": 5, "snapshot_date": "2026-06-12"},  # +50%
        {"ticker": "GOOGL", "downloads_30d": 100.0, "n_models": 5, "snapshot_date": "2026-06-01"},
        {"ticker": "GOOGL", "downloads_30d": 102.0, "n_models": 5, "snapshot_date": "2026-06-12"},  # +2%
        {"ticker": "IBM", "downloads_30d": 100.0, "n_models": 5, "snapshot_date": "2026-06-01"},
        {"ticker": "IBM", "downloads_30d": 90.0, "n_models": 5, "snapshot_date": "2026-06-12"},      # -10%
    ])
    snaps.to_parquet(d / "downloads.parquet")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    rows = altdata.hf_momentum()
    by = {r["ticker"]: r for r in rows}
    assert by["META"]["wow_pct"] == 50.0 and by["META"]["hot"] is True
    assert by["IBM"]["wow_pct"] == -10.0 and by["IBM"]["hot"] is False    # falling -> not hot
    # the channel fires only for the hot riser
    recs = M.channel_records({"hf": rows})
    assert "hf_model_momentum" in recs["META"]["channels"]
    assert "GOOGL" not in recs or "hf_model_momentum" not in recs["GOOGL"]["channels"]


def test_hf_momentum_needs_two_snapshots(tmp_path, monkeypatch):
    from lib import config
    from engine import altdata
    d = tmp_path / "huggingface"
    d.mkdir()
    pd.DataFrame([{"ticker": "META", "downloads_30d": 100.0, "n_models": 5, "snapshot_date": "2026-06-12"}]
                 ).to_parquet(d / "downloads.parquet")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    assert altdata.hf_momentum() == []   # single snapshot -> no velocity -> empty


# ============================================================ DEFERRED sources
def test_unusual_options_channel_fires_on_surge():
    signals = {"unusual_options": [
        {"ticker": "AAA", "vol_oi": 0.9, "mult": 4.0, "put_call": 0.5, "lean": "call-skew", "hot": True},
        {"ticker": "BBB", "vol_oi": 0.2, "mult": 1.1, "put_call": 1.0, "lean": "balanced", "hot": False},
    ]}
    recs = M.channel_records(signals)
    assert recs["AAA"]["channels"] == ["unusual_options"]
    assert "BBB" not in recs or "unusual_options" not in recs["BBB"]["channels"]
    assert M.CHANNEL_WEIGHTS["unusual_options"] == 0.65


def test_unusual_options_engine_over_stored_chains(tmp_path, monkeypatch):
    from lib import config
    from engine import altdata
    d = tmp_path / "polygon_gex" / "chains"
    d.mkdir(parents=True)
    # 5 baseline days at vol/OI ~0.1, then a surge day at ~0.5 (5x) for ZZZ
    for i, day in enumerate(["2026-06-10", "2026-06-11", "2026-06-12", "2026-06-13", "2026-06-14"]):
        pd.DataFrame({"underlying": ["ZZZ", "ZZZ"], "oi": [10000.0, 10000.0], "volume": [1000.0, 1000.0],
                      "is_call": [True, False], "asof": [day, day]}).to_parquet(d / f"{day}.parquet")
    pd.DataFrame({"underlying": ["ZZZ", "ZZZ"], "oi": [10000.0, 10000.0], "volume": [5000.0, 5000.0],
                  "is_call": [True, False], "asof": ["2026-06-15", "2026-06-15"]}).to_parquet(d / "2026-06-15.parquet")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    rows = altdata.unusual_options(min_oi=1000.0)
    z = {r["ticker"]: r for r in rows}["ZZZ"]
    assert z["mult"] >= 3.0 and z["hot"] is True


def test_finnhub_channels():
    signals = {
        "analyst": [{"ticker": "AAA", "bull_ratio": 0.7, "rising": True, "hot": True}],
        "insider_mspr": [{"ticker": "BBB", "mspr": 40.0, "hot": True}],
        "earnings": [{"ticker": "CCC", "surprise_pct": 12.0, "hot": True}],
    }
    recs = M.channel_records(signals)
    assert recs["AAA"]["channels"] == ["analyst_upgrade_cluster"]
    assert recs["BBB"]["channels"] == ["insider_mspr"]
    assert recs["CCC"]["channels"] == ["earnings_beat"]
    # insider_mspr supersedes a weak single insider_buy on the same name
    recs2 = M.channel_records({"insider_mspr": [{"ticker": "DDD", "mspr": 40.0, "hot": True}],
                               "insiders": {"buys": [{"ticker": "DDD", "net_usd": 1.0, "buyers": 1}]}})
    assert recs2["DDD"]["channels"] == ["insider_mspr"]


def test_clinicaltrials_parse_filters_industry():
    from collectors import clinicaltrials
    studies = [
        {"protocolSection": {"identificationModule": {"nctId": "NCT1", "briefTitle": "GLP-1 P3"},
                             "statusModule": {"overallStatus": "RECRUITING",
                                              "studyFirstPostDateStruct": {"date": "2026-06-01"}},
                             "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Lilly", "class": "INDUSTRY"}},
                             "designModule": {"phases": ["PHASE3"]}}},
        {"protocolSection": {"identificationModule": {"nctId": "NCT2"},
                             "statusModule": {"overallStatus": "TERMINATED", "whyStopped": "futility"},
                             "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Some Univ", "class": "OTHER"}},
                             "designModule": {"phases": ["PHASE3"]}}},  # non-industry -> dropped
    ]
    rows = clinicaltrials.parse_studies(studies, "LLY")
    assert len(rows) == 1 and rows[0]["nct"] == "NCT1" and rows[0]["is_halt"] is False


def test_clinical_phase3_channel_and_halt_metric():
    signals = {"clinical": [{"ticker": "LLY", "phase3_starts": 2, "halts": 1, "hot": True}]}
    recs = M.channel_records(signals)
    assert "clinical_phase3_start" in recs["LLY"]["channels"]
    assert recs["LLY"]["clinical_halts"] == 1   # halt carried as a metric, not a bullish channel


def test_polygon_news_parse_and_channel():
    from collectors import polygon_news
    results = [
        {"insights": [{"ticker": "NVDA", "sentiment": "positive"}, {"ticker": "AMD", "sentiment": "negative"}]},
        {"insights": [{"ticker": "NVDA", "sentiment": "positive"}]},
        {"insights": [{"ticker": "NVDA", "sentiment": "neutral"}]},
    ]
    roll = polygon_news.parse_sentiment(results, "NVDA")
    assert roll["articles"] == 3 and roll["bullish"] == 2 and roll["bull_ratio"] == round(2 / 3, 2)
    recs = M.channel_records({"news_sentiment": [{"ticker": "NVDA", "bull_ratio": 0.7, "articles": 8, "hot": True}]})
    assert "news_sentiment" in recs["NVDA"]["channels"]


def test_sam_velocity_and_radar_leg():
    from collectors import sam_gov
    naics_map = {"221113": ["nuclear_power"], "336414": ["defense", "space_economy"]}
    opps = [
        {"naicsCode": "221113", "type": "Presolicitation", "postedDate": "2026-06-10"},   # recent nuclear
        {"naicsCode": "221113", "type": "Solicitation", "postedDate": "2026-03-15"},       # prior nuclear
        {"naicsCode": "336414", "type": "Combined Synopsis/Solicitation", "postedDate": "2026-06-05"},  # defense+space
        {"naicsCode": "221113", "type": "Award Notice", "postedDate": "2026-06-09"},        # award -> excluded
    ]
    vel = sam_gov.velocity(opps, naics_map, today="2026-06-20")
    assert vel.loc["nuclear_power", "recent_count"] == 1 and vel.loc["nuclear_power", "prior_count"] == 1
    assert vel.loc["defense", "recent_count"] == 1 and vel.loc["space_economy", "recent_count"] == 1
    # fuses as a theme_event radar leg
    ta.SOURCES_BY_NAME = {s["name"]: s for s in ta.SOURCES}
    assert "sam_presolicitation" in ta.SOURCES_BY_NAME and ta.SOURCES_BY_NAME["sam_presolicitation"]["kind"] == "theme_event"


def test_github_momentum_channel():
    recs = M.channel_records({"github": [{"ticker": "MSFT", "stars": 1000, "wow_pct": 8.0, "hot": True}]})
    assert "github_momentum" in recs["MSFT"]["channels"]
    assert M.CHANNEL_WEIGHTS["github_momentum"] == 0.30
