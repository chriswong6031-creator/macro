"""D1 census — shared loader + membership-builder module.

Self-contained from a fresh repo checkout with data/ and site/ materialized.
No pickle caches: every consumer calls load()/build_memberships()/build_cohorts()
fresh (a few seconds of pandas work) instead of round-tripping a pickled frame.

Import this from any research/prophet_v4/d1/build/NN_*.py script:
    from _common import REPO, PIN, load, build_memberships, build_cohorts
"""
from __future__ import annotations
import datetime
import json
from pathlib import Path

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[4]
OUTDIR = REPO / "research/prophet_v4/d1"
PIN = "5c1d82b928"

SECTOR_PSEUDO_BASKETS = {
    "us_sector_tech", "us_sector_financials", "us_sector_health", "us_sector_discretionary",
    "us_sector_comm", "us_sector_industrials", "us_sector_staples", "us_sector_energy",
    "us_sector_utilities", "us_sector_realestate", "us_sector_materials",
}


def load() -> dict:
    """Load every core D1 source fresh from the repo checkout. Returns a dict of
    DataFrames/dicts, in-memory only -- nothing is pickled to disk."""
    d = {}

    d["tg_nodes"] = pd.read_parquet(REPO / "data/theme_graph/nodes.parquet")
    d["tg_edges"] = pd.read_parquet(REPO / "data/theme_graph/edges.parquet")
    d["tg_capability"] = pd.read_parquet(REPO / "data/theme_graph/capability.parquet")
    d["tg_evidence"] = pd.read_parquet(REPO / "data/theme_graph/evidence.parquet")
    d["tg_meta"] = json.load(open(REPO / "data/theme_graph/_meta.json"))
    probation = []
    with open(REPO / "data/theme_graph/probation/proposals.jsonl") as f:
        for line in f:
            line = line.strip()
            if line:
                probation.append(json.loads(line))
    d["tg_probation"] = probation

    d["crosswalk"] = yaml.safe_load(open(REPO / "config/theme_crosswalk.yml"))

    d["baskets_membership"] = json.load(open(REPO / "data/baskets/membership.json"))
    d["baskets_history"] = pd.read_parquet(REPO / "data/baskets/membership_history.parquet")
    d["baskets_snapshot"] = json.load(open(REPO / "data/baskets/snapshots/2026-08-13.json"))

    d["cand_2026_08"] = pd.read_parquet(REPO / "data/us_prophet_rank/candidates/2026-08.parquet")
    d["cand_2026_07"] = pd.read_parquet(REPO / "data/us_prophet_rank/candidates/2026-07.parquet")

    d["prophet_index"] = json.load(open(REPO / "site/prophet/index.json"))
    d["turn_watch"] = json.load(open(REPO / "site/turn_watch/turn_watch.json"))
    d["us_standouts"] = json.load(open(REPO / "site/factordata/us_standouts.json"))

    d["ticker_sectors"] = pd.read_parquet(REPO / "data/breadth/ticker_sectors.parquet")
    d["universe_membership"] = pd.read_parquet(REPO / "data/universe/membership.parquet")

    d["si_universe_snapshot"] = pd.read_parquet(REPO / "data/stock_identity/partition/universe_snapshot_v1.parquet")
    d["si_partition_manifest"] = json.load(open(REPO / "data/stock_identity/partition/partition_manifest_v1.json"))
    d["si_gold_amendment"] = json.load(open(REPO / "data/stock_identity/amendments/w1a1_gold_wrong_issuer.json"))

    d["neuralweb_theme_state"] = json.load(open(REPO / "data/neuralweb/theme_state.json"))
    d["group_pulse_episodes"] = pd.read_parquet(REPO / "data/group_pulse/episodes.parquet")
    d["theme_sources"] = yaml.safe_load(open(REPO / "config/theme_sources.yml"))

    tree_asofs = set()
    with open(REPO / "data/themes_heatmap/tree_history.jsonl") as f:
        for line in f:
            line = line.strip()
            if line:
                tree_asofs.add(json.loads(line).get("asof"))
    d["themes_heatmap_tree_asofs"] = sorted(tree_asofs)

    subsector_asofs = set()
    with open(REPO / "data/themes_heatmap/subsector_perf_history.jsonl") as f:
        for line in f:
            line = line.strip()
            if line:
                subsector_asofs.add(json.loads(line).get("asof"))
    d["themes_heatmap_subsector_asofs"] = sorted(subsector_asofs)

    return d


def build_memberships(d: dict) -> dict:
    """Company->{membership-id} sets per source, from theme_graph live MEMBER_OF edges
    (co:us src only) + structural sector data. Returns plain dicts of ticker -> set(str)."""
    from collections import defaultdict

    edges = d["tg_edges"]
    member = edges[(edges["type"] == "MEMBER_OF") & (edges["valid_to"].isna())].copy()
    member["src_prefix"] = member["src"].str.split(":").str[:2].str.join(":")
    member["dst_prefix"] = member["dst"].str.split(":").str[:2].str.join(":")
    us_member = member[member["src_prefix"] == "co:us"].copy()
    us_member["ticker"] = us_member["src"].str.split(":").str[2]
    us_member["dst_basket_id"] = us_member["dst"].str.split(":").str[2]

    crosswalk_themes = d["crosswalk"]["themes"]
    primary_basket_to_theme = {t["primary_basket_id"]: t["id"] for t in crosswalk_themes if t.get("primary_basket_id")}
    all_basket_to_themeids = defaultdict(set)
    for t in crosswalk_themes:
        for bid in (t.get("basket_ids") or []):
            all_basket_to_themeids[bid].add(t["id"])

    canon_membership = defaultdict(set)
    canon_rows = us_member[(us_member["dst_prefix"] == "basket:baskets") & (us_member["dst_basket_id"].isin(primary_basket_to_theme.keys()))]
    for _, row in canon_rows.iterrows():
        canon_membership[row["ticker"]].add(primary_basket_to_theme[row["dst_basket_id"]])

    proxy_membership = defaultdict(set)
    proxy_rows = us_member[(us_member["dst_prefix"] == "basket:baskets") & (us_member["dst_basket_id"].isin(all_basket_to_themeids.keys()))]
    for _, row in proxy_rows.iterrows():
        for tid in all_basket_to_themeids[row["dst_basket_id"]]:
            proxy_membership[row["ticker"]].add(tid)

    curated_membership = defaultdict(set)
    curated_rows = us_member[(us_member["dst_prefix"] == "basket:baskets") & (~us_member["dst_basket_id"].isin(SECTOR_PSEUDO_BASKETS))]
    for _, row in curated_rows.iterrows():
        curated_membership[row["ticker"]].add(row["dst_basket_id"])

    finviz_membership = defaultdict(set)
    for _, row in us_member[us_member["dst_prefix"] == "ltheme:finviz"].iterrows():
        finviz_membership[row["ticker"]].add(row["dst"])

    ths_membership = defaultdict(set)
    for _, row in us_member[us_member["dst_prefix"] == "ltheme:ths"].iterrows():
        ths_membership[row["ticker"]].add(row["dst"])

    ticker_sectors = d["ticker_sectors"]
    structural_membership = defaultdict(set)
    for tk, sec in zip(ticker_sectors["ticker"], ticker_sectors["sector"]):
        structural_membership[tk].add(f"gics:{sec}")
    sector_pseudo_rows = us_member[(us_member["dst_prefix"] == "basket:baskets") & (us_member["dst_basket_id"].isin(SECTOR_PSEUDO_BASKETS))]
    for _, row in sector_pseudo_rows.iterrows():
        structural_membership[row["ticker"]].add(row["dst"])
    cand8 = d["cand_2026_08"]
    cur_0807 = cand8[(cand8["stamp_date"] == "2026-08-07") & (cand8["tier"] == "curated")]
    for tk, sec in zip(cur_0807["ticker"], cur_0807["sector"]):
        if sec is not None and str(sec) != "nan":
            structural_membership[tk].add(f"candidates_sector:{sec}")

    return {
        "canon_membership": dict(canon_membership),
        "proxy_membership": dict(proxy_membership),
        "curated_membership": dict(curated_membership),
        "finviz_membership": dict(finviz_membership),
        "ths_membership": dict(ths_membership),
        "structural_membership": dict(structural_membership),
        "primary_basket_to_theme": primary_basket_to_theme,
        "all_basket_to_themeids": {k: v for k, v in all_basket_to_themeids.items()},
        "SECTOR_PSEUDO_BASKETS": SECTOR_PSEUDO_BASKETS,
    }


def build_cohorts(d: dict, today_session: str = "2026-08-17") -> dict:
    """C0-C5 cohorts (C6 is computed downstream from C0/C1 + memberships). Ticker lists
    are plain python lists (JSON-serializable)."""
    cand8, cand7 = d["cand_2026_08"], d["cand_2026_07"]

    c0_stamp = "2026-08-07"
    c0_rows = cand8[cand8["stamp_date"] == c0_stamp]
    c0_tickers = sorted(set(c0_rows["ticker"].unique()))

    alt_latest_stamp = sorted(cand8["stamp_date"].unique())[-1]
    alt_latest_rows = cand8[cand8["stamp_date"] == alt_latest_stamp]
    c1_tickers = sorted(set(alt_latest_rows["ticker"].unique()))

    plans = d["prophet_index"]["plans"]
    c2_tickers = sorted(set(p["asset"] for p in plans))

    tw = d["turn_watch"]
    deck_tickers = [row["ticker"] for row in tw["deck"]]
    beyond_tickers = [row["ticker"] for row in tw["beyond_cap"]]
    c3_tickers = sorted(set(deck_tickers + beyond_tickers))

    standouts = d["us_standouts"]
    c5_tickers = sorted(set(b["ticker"] for b in standouts["buy"]))

    return {
        "C0": {"tickers": c0_tickers, "session_stamp": c0_stamp, "closed_count": len(c0_tickers)},
        "C1": {"tickers": c1_tickers, "session_stamp": alt_latest_stamp, "closed_count": len(c1_tickers)},
        "C2": {"tickers": c2_tickers, "session_stamp": d["prophet_index"]["source_asof"], "closed_count": len(c2_tickers)},
        "C3": {"tickers": c3_tickers, "session_stamp": tw["as_of"], "closed_count": len(c3_tickers)},
        "C4": {"tickers": [], "session_stamp": "UNKNOWN", "closed_count": None},
        "C5": {"tickers": c5_tickers, "session_stamp": standouts["as_of"], "closed_count": len(c5_tickers)},
    }
