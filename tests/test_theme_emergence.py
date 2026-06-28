"""engine.theme_emergence — fundamental bottleneck DISCOVERY. Verifies the SIC-cluster
logic: a majority-untracked scarcity cluster surfaces as a candidate; mostly-tracked or
too-thin industries do not; velocity is recent-vs-baseline distinct filers. Pure/fixture.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from engine import theme_emergence as te

REF = date(2026, 6, 1)


def _row(tk, sic, days_ago, phrase="on allocation", desc="Test Industry"):
    # default phrase is manufacturing-SPECIFIC so the specificity gate passes; SIC 3xxx
    # (manufacturing) so the domain gate passes
    return {"ticker": tk, "sic": sic, "sic_desc": desc,
            "file_date": str(REF - timedelta(days=days_ago)), "phrase": phrase}


def test_untracked_cluster_is_a_candidate():
    df = pd.DataFrame([_row("ZZA", "3674", 10), _row("ZZB", "3674", 20),
                       _row("ZZC", "3674", 30), _row("ZZD", "3674", 40)])
    cands = te._candidates_from(df, known=set(), ref=REF)
    assert len(cands) == 1
    c = cands[0]
    assert c["sic"] == "3674" and c["n_new_filers"] == 4 and c["n_known_filers"] == 0
    assert set(c["new_filers"]) == {"ZZA", "ZZB", "ZZC", "ZZD"}
    assert c["sic_desc"] == "Test Industry"


def test_majority_tracked_industry_excluded():
    known = {"KN1", "KN2", "KN3"}
    df = pd.DataFrame([_row("KN1", "2080", 10), _row("KN2", "2080", 12),
                       _row("KN3", "2080", 14), _row("ZZA", "2080", 16)])
    assert te._candidates_from(df, known=known, ref=REF) == []   # new share 1/4 < 0.5


def test_below_min_new_filers_excluded():
    df = pd.DataFrame([_row("ZZA", "3559", 10), _row("ZZB", "3559", 20)])  # only 2 new
    assert te._candidates_from(df, known=set(), ref=REF) == []


def test_velocity_recent_vs_baseline():
    df = pd.DataFrame([_row("OLD", "3827", 300),                # baseline (>180d back)
                       _row("ZZA", "3827", 10), _row("ZZB", "3827", 20),
                       _row("ZZC", "3827", 30)])
    cands = te._candidates_from(df, known=set(), ref=REF)
    assert len(cands) == 1
    assert cands[0]["n_new_filers"] == 3          # OLD is baseline, excluded from recent
    assert cands[0]["velocity"] == 2              # 3 recent filers - 1 baseline filer


def test_excluded_polysemy_domain_dropped():
    # REIT (SIC 6798) with 4 untracked filers + a specific phrase -> still excluded by domain
    df = pd.DataFrame([_row("ZZA", "6798", 10), _row("ZZB", "6798", 20),
                       _row("ZZC", "6798", 30), _row("ZZD", "6798", 40)])
    assert te._candidates_from(df, known=set(), ref=REF) == []


def test_polysemous_only_language_dropped():
    # manufacturing SIC but ONLY polysemous language ("sold out"/"supply constrained")
    df = pd.DataFrame([_row("ZZA", "3674", 10, phrase="sold out"),
                       _row("ZZB", "3674", 20, phrase="supply constrained"),
                       _row("ZZC", "3674", 30, phrase="sold out")])
    assert te._candidates_from(df, known=set(), ref=REF) == []
    # one specific phrase rescues it
    df2 = pd.concat([df, pd.DataFrame([_row("ZZD", "3674", 5, phrase="extended lead times")])],
                    ignore_index=True)
    cands = te._candidates_from(df2, known=set(), ref=REF)
    assert len(cands) == 1 and cands[0]["n_new_filers"] == 4


def test_multi_class_counts_one_issuer():
    # two share classes of one issuer share a CIK -> ONE issuer, not two (no threshold inflation)
    def r(tk, cik, days):
        return {"ticker": tk, "cik": cik, "sic": "3674", "sic_desc": "Semis",
                "file_date": str(REF - timedelta(days=days)), "phrase": "on allocation"}
    df = pd.DataFrame([r("AAA", "1", 10), r("GOOG", "2", 12), r("GOOGL", "2", 13), r("BBB", "3", 14)])
    cands = te._candidates_from(df, known=set(), ref=REF)
    assert len(cands) == 1
    assert cands[0]["n_new_filers"] == 3                 # 3 distinct CIKs despite 4 tickers
    assert "GOOG" in cands[0]["new_filers"] and "GOOGL" in cands[0]["new_filers"]


def test_null_sic_dropped_and_empty_is_none():
    df = pd.DataFrame([{"ticker": "ZZA", "sic": None, "sic_desc": None,
                        "file_date": str(REF), "phrase": "sold out"}])
    assert te._candidates_from(df, known=set(), ref=REF) == []
    assert te.compute_theme_emergence(write_ledger=False, hits=pd.DataFrame()) is None
