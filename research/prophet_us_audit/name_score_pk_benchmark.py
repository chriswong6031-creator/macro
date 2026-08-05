"""Frozen-frame P@k benchmark for the name_score composite (US Superintelligence Roadmap §4.4).

THE QUESTION. The US board's displayed ``conviction.score`` IS ``engine/name_score.py``'s
``potential_score`` — ``scripts/build_stock_library.py`` overwrites ``c["score"]`` with
``_pot["score"]`` for backward compatibility — so a multiplicative buy-readiness composite is
live, load-bearing and, until now, unmeasured against the orderings that replaced it. This
instrument ranks the SAME admission cohorts three ways and prints what each one bought.

FRAME. ``data/us_board_ledger/retro_grades.parquet``, ``lane == "buy"``, ``horizon == 10``
(the record basis, the S-A/S-B/S-C frame). Outcome ``excess_spy``; loser threshold stated as
``excess_spy < -3pp at H=10``. Cohort = one ``entry_date`` admission set: every ordering
re-ranks the same names on the same day, so nothing here is an admission study.

THE THREE ORDERINGS
  (a) ``name_score``            the frame's own ``score`` column = the board's displayed
                                conviction score = name_score's ``potential_score``. The
                                identity is VERIFIED in-run against
                                ``data/name_score/us_calls.parquet`` (see ``key_identity``
                                in the results) rather than asserted from the source.
  (b) ``us_prophet_v1_partial`` a PARTIAL, PIT reconstruction of the shipped priority score.
                                ``engine/us_board_rank.py`` (``us_prophet_v1``) was defined
                                2026-08-02, AFTER this frame's era, so no row carries a
                                stamped v1 score — this is an explicit counterfactual built
                                from PIT inputs only, never a recovered stamp:
                                  · signal (30 pts) — tier + tick age RECOMPUTED point-in-
                                    time via ``confluence_tiers.tier_stream`` (the ledger
                                    stamped ``tier_cascade`` on 34/403 rows; stamping began
                                    ~07-16 — the same era-fragmentation the S-B stand-in hit)
                                  · entry  (25 pts) — the ledger's stamped ``entry_status``
                                  · edge   (25 pts) — ``alpha_percentiles`` + ``edge_value``
                                    over the cohort, the module's own functions
                                  · runway (10 pts) — NOT RECONSTRUCTABLE: ``ext_z`` is
                                    absent from the ledger schema. Scored 0 for every row by
                                    the module's own fail-closed rule (unknown evidence never
                                    earns points), so the leg is DARK, not neutral.
                                  · quality(10 pts) — NOT RECONSTRUCTABLE: ``coiled`` /
                                    ``washout_ctx`` are absent. Same treatment.
                                80 of 100 points are attainable. Because two legs are dark
                                for EVERY row they cannot reorder anything — the ranking is
                                signal+entry+edge. Read (b) as "what the reconstructable
                                three-quarters of us_prophet_v1 would have ordered", never as
                                "what us_prophet_v1 scored". The score-leg functions are
                                imported, never re-implemented.
  (c) ``alpha_pctile``          the selection axis alone, as the module's own
                                ``alpha_percentiles`` computes it inside each cohort.

METHOD GUARDS (copied from ``superintelligence_standins.py``)
  · date-demeaned outcomes reported beside raw ones;
  · per-name-first medians reported beside pooled medians;
  · the loser threshold is stated, and medians are reported so no verdict hangs on it;
  · a cohort contributes to P@k only when it holds at least ``2k`` rows, so a "precision"
    can never be an arithmetic certainty from a cohort barely deeper than k. Excluded
    cohorts are COUNTED, never silently dropped;
  · empty denominators print ``null`` with a reason. A null is not 0.5 and not 0.

Exploratory. This ranks the adjudication queue (roadmap §4.4: demote / mine the legs /
keep-with-its-card); it confers no authority on anything and changes no gate.

Run:  python3 research/prophet_us_audit/name_score_pk_benchmark.py
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
                   "name_score_pk_benchmark_results.json")
os.chdir(REPO)
sys.path.insert(0, REPO)

FRAME = "data/us_board_ledger/retro_grades.parquet"
NAME_SCORE_LEDGER = "data/name_score/us_calls.parquet"
UNIVERSE_GROUPS = ("breadth", "midcap_breadth", "smallcap_breadth")

LOSER_PP = -3.0            # loser := excess_spy < -3pp at H=10 (stated, not tuned)
KS = (1, 3, 5, 10)
MIN_COHORT_MULT = 2        # a cohort must hold >= 2k rows to contribute to P@k


# --------------------------------------------------------------------------- #
# frame
# --------------------------------------------------------------------------- #
def load_frame() -> pd.DataFrame:
    df = pd.read_parquet(FRAME)
    df = df[(df["lane"] == "buy") & (df["horizon"] == 10)].copy()
    df = df.dropna(subset=["excess_spy", "entry_date", "ticker"])
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["excess_pp"] = df["excess_spy"] * 100.0
    df["excess_dm"] = df["excess_pp"] - df.groupby("entry_date")["excess_pp"].transform("mean")
    df["loser"] = df["excess_pp"] < LOSER_PP
    return df.reset_index(drop=True)


def verify_key_identity(df: pd.DataFrame) -> dict:
    """Measure the claim the roadmap makes in prose: the board's ``score`` IS name_score's
    ``potential_score``.

    The grader stamps its call ledger with ``asof = utcnow().date()`` — the build runs after
    the board's own ``as_of`` close — so the ledger date lines up with the board row's
    ``entry_date``, not its ``as_of``. Both alignments are measured and reported; the
    mismatched rows are counted per date so a join artifact (a long weekend shifting the
    build date past the next session) cannot be read as a score divergence.
    """
    out: dict = {"ledger": NAME_SCORE_LEDGER,
                 "claim": "board conviction.score == name_score.potential_score "
                          "(scripts/build_stock_library.py overwrites c['score'] with "
                          "the potential score for backward compatibility)"}
    try:
        ns = pd.read_parquet(NAME_SCORE_LEDGER)[["date", "ticker", "score"]]
    except Exception as exc:  # noqa: BLE001
        out["status"] = f"unverified — ledger unreadable: {exc}"
        return out
    ns = ns.rename(columns={"score": "ns_score"})
    ns["date"] = ns["date"].astype(str)
    b = df[["as_of", "entry_date", "ticker", "score"]].copy()
    b["as_of"] = b["as_of"].astype(str)
    b["entry_date"] = b["entry_date"].dt.strftime("%Y-%m-%d")
    for key in ("entry_date", "as_of"):
        j = b.merge(ns.rename(columns={"date": key}), on=[key, "ticker"], how="inner")
        cell: dict = {"n_joined": int(len(j))}
        if len(j):
            eq = j["score"] == j["ns_score"]
            cell.update({
                "exact_match_rate": round(float(eq.mean()), 3),
                "spearman": round(float(j["score"].rank().corr(j["ns_score"].rank())), 4),
                "n_mismatch": int((~eq).sum()),
                "mismatch_by_date": {str(k): int(v) for k, v in
                                     j.loc[~eq, key].value_counts().sort_index().items()},
            })
        out[f"join_on_{key}"] = cell
    out["note"] = ("the ledger overlaps only the tail of this frame (the name_score store "
                   "begins after the frame's first cohorts), so the receipt is a partial "
                   "verification of a full-frame identity — stated, not glossed")
    return out


# --------------------------------------------------------------------------- #
# ordering (b): us_prophet_v1 partial reconstruction
# --------------------------------------------------------------------------- #
def _close_panel() -> pd.DataFrame:
    P = pd.concat([pd.read_parquet(f"data/{g}/_closes_cache.parquet")
                   for g in UNIVERSE_GROUPS], axis=1)
    return P.loc[:, ~P.columns.duplicated()]


def recompute_tiers(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """PIT tier + tick age at admission, from the production ``tier_stream`` (S-B's idiom).

    The stored frame carries ``tier_cascade`` on a small minority of rows because tier
    stamping began mid-frame; recomputing it is what makes the signal leg readable at all.
    """
    from engine import confluence_tiers as ct
    P = _close_panel()
    cache: dict[str, pd.DataFrame] = {}
    tiers: list[str | None] = []
    ticks: list[float | None] = []
    for _, r in df.iterrows():
        t, d = r["ticker"], r["entry_date"]
        if t not in P.columns:
            tiers.append(None)
            ticks.append(None)
            continue
        if t not in cache:
            cache[t] = ct.tier_stream(P[t].dropna())
        st = cache[t]
        if st.empty or d not in st.index:
            tiers.append(None)
            ticks.append(None)
            continue
        row = st.loc[d]
        tiers.append(row["tier"])
        ticks.append(float(row["ticks"]) if pd.notna(row["ticks"]) else None)
    df = df.copy()
    df["pit_tier"] = tiers
    df["pit_ticks"] = ticks
    cov = {
        "basis": "engine.confluence_tiers.tier_stream (completed buckets, raw-3D-cross T1)",
        "n_rows": int(len(df)),
        "n_pit_tier": int(df["pit_tier"].notna().sum()),
        "n_stamped_tier_cascade": int(df["tier_cascade"].notna().sum()),
        "pit_tier_hist": {str(k): int(v) for k, v in
                          df["pit_tier"].value_counts(dropna=False).items()},
    }
    return df, cov


def build_v1_partial(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Score every row with us_prophet_v1's OWN leg functions, over the legs this frame can
    supply. Returns the frame plus a coverage/disclosure block naming the dark legs."""
    from engine import us_board_rank as ubr
    df = df.copy()
    df["v1_partial"] = np.nan
    df["alpha_pctile"] = np.nan
    parts = {"signal": [], "entry": [], "edge": []}
    for _d, sub in df.groupby("entry_date"):
        rows = [{"ticker": r["ticker"], "alpha": r["alpha"]} for _, r in sub.iterrows()]
        pct = ubr.alpha_percentiles(rows)
        for i, (idx, r) in enumerate(sub.iterrows()):
            sig = ubr.signal_value({"tier_cascade": r.get("pit_tier"),
                                    "ticks": r.get("pit_ticks"),
                                    "provisional": False})
            ent = ubr.entry_value({"status": r.get("entry_status")})
            edg = ubr.edge_value(pct.get(i))
            df.at[idx, "alpha_pctile"] = (np.nan if pct.get(i) is None else pct[i])
            df.at[idx, "v1_partial"] = (ubr.SCORE_WEIGHTS["signal"] * sig
                                        + ubr.SCORE_WEIGHTS["entry"] * ent
                                        + ubr.SCORE_WEIGHTS["edge"] * edg)
            parts["signal"].append(sig)
            parts["entry"].append(ent)
            parts["edge"].append(edg)
    disclosure = {
        "definition_date": "2026-08-02 — AFTER this frame's era; no row carries a stamped "
                           "us_prophet_v1 score, so this ordering is an explicit "
                           "counterfactual from PIT inputs, never a recovered stamp",
        "attainable_points": 80.0,
        "legs_scored": {
            "signal": {"weight": ubr.SCORE_WEIGHTS["signal"],
                       "source": "PIT tier_stream recompute",
                       "n_nonzero": int(sum(1 for v in parts["signal"] if v > 0))},
            "entry": {"weight": ubr.SCORE_WEIGHTS["entry"],
                      "source": "ledger entry_status (stamped)",
                      "n_nonzero": int(sum(1 for v in parts["entry"] if v > 0))},
            "edge": {"weight": ubr.SCORE_WEIGHTS["edge"],
                     "source": "us_board_rank.alpha_percentiles + edge_value over the cohort",
                     "n_nonzero": int(sum(1 for v in parts["edge"] if v > 0))},
        },
        "legs_dark": {
            "runway": {"weight": ubr.SCORE_WEIGHTS["runway"],
                       "reason": "ext_z is absent from the retro_grades schema — scored 0 for "
                                 "every row by the module's fail-closed rule; a dark leg "
                                 "cannot reorder anything, it only lowers the ceiling"},
            "quality": {"weight": ubr.SCORE_WEIGHTS["quality"],
                        "reason": "coiled / washout_ctx are absent from the retro_grades "
                                  "schema — same treatment"},
        },
        "n_rows": int(len(df)),
        "n_scored": int(df["v1_partial"].notna().sum()),
    }
    return df, disclosure


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _cell(m: pd.DataFrame) -> dict:
    byname = m.groupby("ticker")["excess_pp"].median()
    return {
        "n": int(len(m)),
        "names": int(byname.shape[0]),
        "loser_rate_pct": round(float(m["loser"].mean() * 100), 1),
        "median_excess_pp": round(float(m["excess_pp"].median()), 2),
        "median_excess_dm_pp": round(float(m["excess_dm"].median()), 2),
        "per_name_median_pp": round(float(byname.median()), 2),
    }


def _expected_pk(sub: pd.DataFrame, col: str, k: int) -> tuple[float, int, float]:
    """P@k of one cohort, EXACT under ties: the expected hit share of a uniformly random
    top-k draw from the tie group at the k-th boundary.

    Why this and not ``sort_values([col, "ticker"]).head(k)``: the name_score column ties 6
    and 7 names at 100 on the frame's two largest cohorts, so an alphabetical tie-break
    would have decided 2 of the 10 P@1 observations by ticker spelling and the headline
    would be an artifact of the sort key. Taking the expectation over the tie group states
    exactly what the ordering knows and no more.
    """
    s = sub.sort_values(col, ascending=False)
    vals = s[col].to_numpy(dtype="float64")
    hits = s["hit"].to_numpy(dtype="float64")
    boundary = float(vals[k - 1])
    above = vals > boundary
    tied = vals == boundary
    take_from_tie = k - int(above.sum())
    exp_hits = float(hits[above].sum()) + float(hits[tied].sum()) * take_from_tie / int(tied.sum())
    return exp_hits / k, int(tied.sum()), boundary


def pk_table(df: pd.DataFrame, col: str, *, perm_b: int = 20000, seed: int = 20260804) -> dict:
    """P@k for one ordering over the shared admission cohorts.

    ``hit`` = the row's excess beats ITS OWN cohort's median excess (date-demeaned by
    construction). The cohort-wide base rate is reported beside every k, measured rather
    than assumed, so a lift is read against the cohort the picks came from.

    ``perm_p_one_sided`` answers the only question a 10-cohort P@k can support: how often
    does a RANDOM ordering of these same cohorts reach this precision or better? The null
    draws each cohort's top-k as a uniform random subset (hypergeometric on that cohort's
    own hit count), so it inherits the frame's cohort sizes and base rates exactly. It is a
    disclosure of thinness, not a significance gate — nothing here passes or fails on it.
    """
    out: dict = {
        "ordering": col,
        "hit_definition": "excess_spy beats that admission cohort's median excess_spy",
        "loser_definition": f"excess_spy < {LOSER_PP}pp at H=10",
        "min_cohort_rule": f"a cohort contributes to P@k only with >= {MIN_COHORT_MULT}k rows",
        "tie_handling": "expected hit share of a uniformly random draw from the tie group at "
                        "the k-th boundary — never an alphabetical tie-break",
        "perm_null": "each cohort's top-k drawn as a uniform random subset of that cohort "
                     f"(B={perm_b}, seed={seed}); one-sided, disclosure only",
        "by_k": {},
    }
    usable = df.dropna(subset=[col])
    out["n_rows_ranked"] = int(len(usable))
    out["n_rows_unrankable"] = int(len(df) - len(usable))
    rng = np.random.RandomState(seed)
    for k in KS:
        picks, bases, ties, kept, skipped = [], [], [], 0, 0
        pools: list[pd.DataFrame] = []
        null_draws: list[np.ndarray] = []
        per_cohort: dict[str, float] = {}
        for _d, sub in usable.groupby("entry_date"):
            if len(sub) < MIN_COHORT_MULT * k:
                skipped += 1
                continue
            kept += 1
            med = float(sub["excess_pp"].median())
            sub = sub.assign(hit=sub["excess_pp"] > med)
            p, n_tie, boundary = _expected_pk(sub, col, k)
            picks.append(p)
            per_cohort[str(pd.Timestamp(_d).date())] = round(p, 3)
            ties.append(n_tie)
            bases.append(float(sub["hit"].mean()))
            # the pool a top-k is drawn from under ties — reported so an inflated n is visible
            pools.append(sub[sub[col] >= boundary])
            n_hits = int(sub["hit"].sum())
            null_draws.append(rng.hypergeometric(n_hits, len(sub) - n_hits, k,
                                                 size=perm_b) / k)
        if not picks:
            out["by_k"][f"p_at_{k}"] = {
                "value": None, "n_cohorts": 0, "n_cohorts_skipped_thin": skipped,
                "null_reason": f"no cohort holds {MIN_COHORT_MULT * k}+ rows — P@{k} is not "
                               f"computable here, which is not the same as 0.5",
            }
            continue
        obs = float(np.mean(picks))
        null = np.mean(np.vstack(null_draws), axis=0)
        pool_all = pd.concat(pools)
        out["by_k"][f"p_at_{k}"] = {
            "value": round(obs, 3),
            "base_rate": round(float(np.mean(bases)), 3),
            "lift_vs_base": round(obs - float(np.mean(bases)), 3),
            "n_cohorts": kept,
            "n_cohorts_skipped_thin": skipped,
            "perm_p_one_sided": round(float((1 + int((null >= obs - 1e-12).sum()))
                                            / (perm_b + 1)), 4),
            "tie_depth_at_k": {"mean": round(float(np.mean(ties)), 2), "max": int(max(ties))},
            "per_cohort": per_cohort,
            "pick_pool": _cell(pool_all),
        }
    return out


def ic_table(df: pd.DataFrame, col: str) -> dict:
    """Rank-IC three ways, each labelled: the cross-sectional (date-demeaned) IC that a
    ranker is actually judged on, plus both pooled reads so a date effect cannot hide."""
    usable = df.dropna(subset=[col])
    ics, ns = [], []
    for _d, sub in usable.groupby("entry_date"):
        if sub[col].nunique() >= 5 and len(sub) >= 5:
            ics.append(float(sub[col].rank().corr(sub["excess_pp"].rank())))
            ns.append(int(len(sub)))
    out = {
        "ordering": col,
        "rank_ic_by_date": (round(float(np.mean(ics)), 4) if ics else None),
        "rank_ic_by_date_median": (round(float(np.median(ics)), 4) if ics else None),
        "n_ic_cohorts": len(ics),
        "cohort_sizes": ({"min": min(ns), "median": int(np.median(ns)), "max": max(ns)}
                         if ns else None),
        "per_cohort_ic": [round(x, 4) for x in ics],
    }
    if len(usable) >= 5:
        out["rank_ic_pooled_raw"] = round(
            float(usable[col].rank().corr(usable["excess_pp"].rank())), 4)
        out["rank_ic_pooled_demeaned"] = round(
            float(usable[col].rank().corr(usable["excess_dm"].rank())), 4)
    else:
        out["rank_ic_pooled_raw"] = None
        out["rank_ic_pooled_demeaned"] = None
        out["null_reason"] = "fewer than 5 rankable rows"
    if not ics:
        out["null_reason"] = ("no cohort carries 5+ distinct values — the cross-sectional "
                              "rank-IC is not computable (null, not zero)")
    return out


def cross_ordering_agreement(df: pd.DataFrame, cols: list[str]) -> dict:
    """How much of any difference between two orderings is real: their within-cohort rank
    agreement. Two orderings that agree at rho ~ 1 cannot disagree about P@k for a reason."""
    out: dict = {}
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            rhos = []
            for _d, sub in df.dropna(subset=[a, b]).groupby("entry_date"):
                if len(sub) >= 5 and sub[a].nunique() >= 2 and sub[b].nunique() >= 2:
                    rhos.append(float(sub[a].rank().corr(sub[b].rank())))
            out[f"{a}__vs__{b}"] = {
                "mean_within_cohort_spearman": (round(float(np.mean(rhos)), 4)
                                                if rhos else None),
                "n_cohorts": len(rhos),
            }
    return out


# --------------------------------------------------------------------------- #
def main() -> None:
    df = load_frame()
    cohort_sizes = df.groupby("entry_date").size()
    res: dict = {
        "instrument": "research/prophet_us_audit/name_score_pk_benchmark.py",
        "roadmap": "research/PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md §4.4 action 2",
        "tier": "research — exploratory; confers no authority and changes no gate",
        "frame": {
            "source": FRAME,
            "filter": "lane == 'buy' and horizon == 10",
            "rows": int(len(df)),
            "names": int(df["ticker"].nunique()),
            "entry_dates": [str(df["entry_date"].min().date()),
                            str(df["entry_date"].max().date())],
            "n_cohorts": int(len(cohort_sizes)),
            "cohort_sizes": {str(k.date()): int(v) for k, v in cohort_sizes.items()},
            "loser_def": f"excess_spy < {LOSER_PP}pp at H=10",
            "base_loser_rate_pct": round(float(df["loser"].mean() * 100), 1),
            "base_median_excess_pp": round(float(df["excess_pp"].median()), 2),
            "era_caveat": "the frame ENDS the day the cascade inclusion gate began "
                          "(2026-07-16); era + n caveats bind every cell below",
        },
    }
    res["key_identity"] = verify_key_identity(df)

    df, tier_cov = recompute_tiers(df)
    df, v1_disc = build_v1_partial(df)
    res["us_prophet_v1_partial"] = {"tier_recompute": tier_cov, **v1_disc}

    orderings = ["score", "v1_partial", "alpha_pctile"]
    labels = {"score": "name_score potential_score (= board conviction.score)",
              "v1_partial": "us_prophet_v1 partial reconstruction (signal+entry+edge)",
              "alpha_pctile": "alpha percentile inside the cohort"}
    res["orderings"] = labels
    res["precision_at_k"] = {c: pk_table(df, c) for c in orderings}
    res["rank_ic"] = {c: ic_table(df, c) for c in orderings}
    res["ordering_agreement"] = cross_ordering_agreement(df, orderings)

    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=str)

    # ---- console verdict table (the PR body's source) ----
    print(json.dumps({k: res[k] for k in ("frame", "key_identity")}, indent=1, default=str))
    print("\nORDERING                                  P@1    P@3    P@5    P@10   "
          "IC(date)  IC(pooled/dm)")
    for c in orderings:
        pk, ic = res["precision_at_k"][c], res["rank_ic"][c]

        def _v(k):
            cell = pk["by_k"][f"p_at_{k}"]
            return "  n/a" if cell["value"] is None else f"{cell['value']:5.3f}"
        print(f"{labels[c][:40]:40s} {_v(1)}  {_v(3)}  {_v(5)}  {_v(10)}  "
              f"{ic['rank_ic_by_date']:+.4f}   {ic['rank_ic_pooled_demeaned']:+.4f}")
    print("\npermutation p (a random ordering of the same cohorts reaching this P@k or better):")
    for c in orderings:
        pk = res["precision_at_k"][c]
        print(f"  {c:14s} " + "  ".join(
            f"k={k}:{pk['by_k'][f'p_at_{k}'].get('perm_p_one_sided')}" for k in KS)
            + f"   [base {pk['by_k']['p_at_1'].get('base_rate')}, "
              f"{pk['by_k']['p_at_1'].get('n_cohorts')} cohorts]")
    print("\ntie depth at the k-th boundary (1 = no tie; the pool a top-k is drawn from):")
    for c in orderings:
        pk = res["precision_at_k"][c]
        print(f"  {c:14s} " + "  ".join(
            f"k={k}:{pk['by_k'][f'p_at_{k}'].get('tie_depth_at_k')}" for k in (1, 5)))
    print("\ntop-k pick pool (k=5): loser rate / median excess / date-demeaned / per-name")
    for c in orderings:
        cell = res["precision_at_k"][c]["by_k"]["p_at_5"]
        if cell["value"] is None:
            print(f"  {c:14s} null — {cell['null_reason']}")
            continue
        p = cell["pick_pool"]
        print(f"  {c:14s} n={p['n']:3d} names={p['names']:3d} "
              f"loser={p['loser_rate_pct']:5.1f}%  median={p['median_excess_pp']:+.2f}pp  "
              f"dm={p['median_excess_dm_pp']:+.2f}pp  per-name={p['per_name_median_pp']:+.2f}pp")
    print(f"  FRAME BASE     n={len(df):3d} names={df['ticker'].nunique():3d} "
          f"loser={df['loser'].mean() * 100:5.1f}%  "
          f"median={df['excess_pp'].median():+.2f}pp")
    print(f"\nordering agreement (within-cohort Spearman): "
          f"{json.dumps(res['ordering_agreement'], default=str)}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    import warnings

    warnings.filterwarnings("ignore")
    main()
