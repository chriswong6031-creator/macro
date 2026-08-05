"""Frozen-frame stand-ins for the US Superintelligence Roadmap (§5 S-A/S-B/S-C).

Frame: data/us_board_ledger/retro_grades.parquet, lane=="buy", horizon==10 (the record
basis). Outcome: excess_spy. All read-only; results JSON written next to this file.

S-A  turnover_pctile_60d at admission (CN's surviving flow axis) vs outcome.
S-B  confirmation pricing: outcome by tier_cascade and, where joinable, cross age.
S-C  ex-ante intel: curated-basket membership at admission vs outcome.

Method guards: date-demeaned deltas beside raw; per-name-first medians beside pooled;
loser := excess_spy < -3pp at H (threshold stated, medians reported so the verdict never
hangs on the threshold). Exploratory stand-ins — rank the ladder queue, confer nothing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "superintelligence_standins_results.json")
os.chdir(REPO)
sys.path.insert(0, REPO)

LOSER_PP = -3.0


def load_frame() -> pd.DataFrame:
    df = pd.read_parquet("data/us_board_ledger/retro_grades.parquet")
    df = df[(df["lane"] == "buy") & (df["horizon"] == 10)].copy()
    df = df.dropna(subset=["excess_spy", "entry_date", "ticker"])
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["excess_pp"] = df["excess_spy"] * 100.0
    # date-demeaned outcome (within admission-date cohort)
    df["excess_dm"] = df["excess_pp"] - df.groupby("entry_date")["excess_pp"].transform("mean")
    df["loser"] = df["excess_pp"] < LOSER_PP
    return df


def load_vol() -> pd.DataFrame:
    vol = [pd.read_parquet(f"data/{g}/_volume_cache.parquet")
           for g in ("breadth", "midcap_breadth", "smallcap_breadth")]
    idx = sorted(set().union(*[set(v.index) for v in vol]))
    V = pd.concat([v.reindex(idx) for v in vol], axis=1)
    return V.loc[:, ~V.columns.duplicated()]


def band_table(df: pd.DataFrame, col: str, bands: list[tuple[str, float, float]]) -> list[dict]:
    rows = []
    for name, lo, hi in bands:
        m = df[(df[col] >= lo) & (df[col] < hi)]
        if len(m) < 5:
            rows.append({"band": name, "n": int(len(m))})
            continue
        byname = m.groupby("ticker")["excess_pp"].median()
        rows.append({
            "band": name, "n": int(len(m)), "names": int(byname.shape[0]),
            "loser_rate_pct": round(float(m["loser"].mean() * 100), 1),
            "median_excess_pp": round(float(m["excess_pp"].median()), 2),
            "median_excess_dm_pp": round(float(m["excess_dm"].median()), 2),
            "per_name_median_pp": round(float(byname.median()), 2),
        })
    return rows


def main() -> None:
    df = load_frame()
    res: dict = {
        "frame": {"rows": int(len(df)), "names": int(df["ticker"].nunique()),
                  "dates": [str(df["entry_date"].min().date()),
                            str(df["entry_date"].max().date())],
                  "loser_def": f"excess_spy < {LOSER_PP}pp at H=10",
                  "base_loser_rate_pct": round(float(df["loser"].mean() * 100), 1),
                  "base_median_excess_pp": round(float(df["excess_pp"].median()), 2)},
    }
    V = load_vol()

    # ---- S-A: admission-day volume percentile in own trailing window ----
    # COVERAGE DEBT, NAMED: the volume caches carry only ~51 non-null sessions
    # (backfilled 2026-05-19; padded to the price index) — the CN-matching 60d
    # spec is unrunnable on this frame until the cache deepens (~mid-Aug 2026).
    # Primary here = own-20d percentile (stated variant), 60d re-run chartered.
    tp = []
    for _, r in df.iterrows():
        t, d = r["ticker"], r["entry_date"]
        if t not in V.columns:
            tp.append(np.nan)
            continue
        s = V[t].dropna()
        pos = s.index.searchsorted(d, side="right") - 1
        if pos < 20:
            tp.append(np.nan)
            continue
        win = s.iloc[pos - 19: pos + 1]
        tp.append(float((win.rank(pct=True)).iloc[-1]))
    df["turnover_pctile_20d"] = tp
    sa = df.dropna(subset=["turnover_pctile_20d"])
    res["S_A_turnover"] = {
        "variant": "own-20d percentile (60d spec data-blocked; debt named above)",
        "coverage": f"{len(sa)}/{len(df)}",
        "bands": band_table(sa, "turnover_pctile_20d", [
            ("<=p50", -0.01, 0.50), ("p50-90", 0.50, 0.90), (">=p90", 0.90, 1.01)]),
        "cn_reference": "CN (60d spec): >=p90 42.5% loser vs <p50 17.7% (monotone)",
    }

    # ---- S-B: confirmation pricing — tier RECOMPUTED at admission via tier_stream ----
    # The stored frame never stamped tier (369/403 null; stamping began ~07-16): the
    # context-vector argument in one sentence. Recompute PIT per-day tier for every
    # episode from the production stream (raw-3D-cross T1 basis, completed buckets).
    from engine import confluence_tiers as ct
    P = pd.concat([pd.read_parquet(f"data/{g}/_closes_cache.parquet")
                   for g in ("breadth", "midcap_breadth", "smallcap_breadth")], axis=1)
    P = P.loc[:, ~P.columns.duplicated()]
    tier_cache: dict[str, pd.DataFrame] = {}
    def tier_at(t: str, d) -> tuple[str | None, float | None]:
        if t not in P.columns:
            return None, None
        if t not in tier_cache:
            st = ct.tier_stream(P[t].dropna())
            tier_cache[t] = st
        st = tier_cache[t]
        if st.empty or d not in st.index:
            return None, None
        row = st.loc[d]
        return (row["tier"], float(row["ticks"]) if pd.notna(row["ticks"]) else None)
    tiers, ticks = [], []
    for _, r in df.iterrows():
        a, b = tier_at(r["ticker"], r["entry_date"])
        tiers.append(a)
        ticks.append(b)
    df["adm_tier"] = tiers
    df["adm_ticks"] = ticks
    sb = []
    for tier in ("T1", "T2", "T3", "T4", None):
        m = df[df["adm_tier"].isna()] if tier is None else df[df["adm_tier"] == tier]
        if len(m) < 5:
            sb.append({"tier": tier or "not_eligible_that_day", "n": int(len(m))})
            continue
        byname = m.groupby("ticker")["excess_pp"].median()
        sb.append({"tier": tier or "not_eligible_that_day", "n": int(len(m)),
                   "loser_rate_pct": round(float(m["loser"].mean() * 100), 1),
                   "median_excess_pp": round(float(m["excess_pp"].median()), 2),
                   "median_excess_dm_pp": round(float(m["excess_dm"].median()), 2),
                   "per_name_median_pp": round(float(byname.median()), 2)})
    # cross-age slice inside eligible admissions (ticks 0 vs 1 vs 2)
    ages = []
    el = df.dropna(subset=["adm_tier"])
    for a in (0.0, 1.0, 2.0):
        m = el[el["adm_ticks"] == a]
        if len(m) < 5:
            ages.append({"ticks": int(a), "n": int(len(m))})
            continue
        ages.append({"ticks": int(a), "n": int(len(m)),
                     "loser_rate_pct": round(float(m["loser"].mean() * 100), 1),
                     "median_excess_pp": round(float(m["excess_pp"].median()), 2),
                     "median_excess_dm_pp": round(float(m["excess_dm"].median()), 2)})
    res["S_B_confirmation"] = {
        "basis": "tier recomputed PIT via confluence_tiers.tier_stream (raw-cross T1); "
                 "stored frame had tier on only 34/403 rows — a finding in itself",
        "by_tier": sb,
        "by_cross_age_ticks": ages,
        "note": "CN-RC0 predicts less-confirmed admissions price better.",
    }

    # ---- S-C: curated-basket membership at admission ----
    memb = json.load(open("data/baskets/membership.json")).get("baskets", {})
    member_of: dict[str, int] = {}
    for _bid, b in memb.items():
        if str(_bid).startswith("us_sector_"):
            continue                      # GICS pseudo-baskets are not curation
        for m in b.get("members", []):
            if not m.get("removed"):
                member_of[m["ticker"]] = member_of.get(m["ticker"], 0) + 1
    df["curated_member"] = df["ticker"].map(lambda t: member_of.get(t, 0) > 0)
    sc = []
    for label, mask in (("member", df["curated_member"]), ("non_member", ~df["curated_member"])):
        m = df[mask]
        byname = m.groupby("ticker")["excess_pp"].median()
        sc.append({"cohort": label, "n": int(len(m)), "names": int(byname.shape[0]),
                   "loser_rate_pct": round(float(m["loser"].mean() * 100), 1),
                   "median_excess_pp": round(float(m["excess_pp"].median()), 2),
                   "median_excess_dm_pp": round(float(m["excess_dm"].median()), 2),
                   "per_name_median_pp": round(float(byname.median()), 2)})
    res["S_C_curated_membership"] = {
        "cohorts": sc,
        "cn_reference": "CN: members 13.1% loser vs non-members 36.2%",
        "caveat": "membership read from TODAY's membership.json (added/removed dates exist "
                  "but current-state read; PIT caveat stated — CN found curated membership "
                  "is PIT-dated enough for an ex-ante receipt)",
    }

    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
