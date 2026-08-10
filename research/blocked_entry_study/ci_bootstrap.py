"""Date-clustered bootstrap CIs for the blocked-entry study (US arm, exit (a)).

NOTE ON INPUT: events_anchor0.parquet does NOT carry the per-ATR-multiple exit results —
study.py strips dict-valued fields when it writes that file, so a_R/a_ret never landed in it.
This script therefore regenerates the event dicts by calling study.events_for_symbol (imported
unmodified). That call is deterministic — same anchor and stable digest-derived per-symbol
placebo RNG — so it reproduces the identical event set behind results.json.

Cluster unit = entry_date (what study.py's median_of_per_date_medians already clusters on;
it is the fire's known_ts advanced one session, so the clusters are in bijection with fire
dates). Resampling is WITH REPLACEMENT over distinct dates, B=2000, numpy seed 20260810.
Difference tests resample the UNION of both arms' dates ONCE per draw so both arms are
evaluated on the same sampled dates.

Statistics: (i) mean R across all fires falling on the sampled dates; (ii) the registered
equal-date-weighted expectancy (mean of each date's mean R); and (iii) median of the per-date
median R as a descriptive tail-shape diagnostic. CIs are 2.5/97.5 percentiles of the draws.
"""
from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd

import study as S

B = 2000
SEED = 20260810
HERE = Path(__file__).resolve().parent
PARAMS = {"primary_m0.5_sysAB": ("m0.5", "sysAB"), "frozen_m1.0_sysA": ("m1.0", "sysA")}


def collect() -> pd.DataFrame:
    syms = S.resolve_universe("full")
    with mp.Pool(20) as pool:
        chunks = pool.map(S._worker, [(s, S.ANCHOR) for s in syms], chunksize=8)
    rows = []
    for c in chunks:
        for e in c:
            if e["market"] != "US":
                continue
            r = {"arm": e["arm"], "entry_date": e["entry_date"], "known_ts": e["known_ts"],
                 "washout": bool(e["total_washout"]),
                 "era": "design" if e["entry_date"] <= S.DESIGN_END else "verdict"}
            for key, _ in PARAMS.values():
                r[f"R_{key}"] = e[key]["a_R"]
            rows.append(r)
    df = pd.DataFrame(rows)
    # systemic flags come from the central SPY join, which study.main does after the pool;
    # redo it here on the same series so the flags match results.json exactly.
    st = S.spy_state()
    # events carry known_ts -> but we clustered on entry_date; re-derive systemic from the
    # SPY state as of the session BEFORE entry (== known_ts), matching study.main.
    return df, st


def _prep(sub: pd.DataFrame, rcol: str) -> pd.DataFrame:
    s = sub[["entry_date", rcol]].dropna()
    g = s.groupby("entry_date")[rcol]
    return pd.DataFrame({"sum": g.sum(), "n": g.size(), "mean": g.mean(), "med": g.median()})


def _draw(n_dates: int, rng) -> np.ndarray:
    return rng.integers(0, n_dates, size=(B, n_dates))


def _stats(tab: pd.DataFrame, dates: pd.Index, idx: np.ndarray):
    a = tab.reindex(dates)
    sm = a["sum"].fillna(0).to_numpy(float)
    nn = a["n"].fillna(0).to_numpy(float)
    av = a["mean"].to_numpy(float)
    md = a["med"].to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_draws = sm[idx].sum(1) / nn[idx].sum(1)
        date_mean_draws = np.nanmean(av[idx], axis=1)
        med_draws = np.nanmedian(md[idx], axis=1)
    point_mean = sm.sum() / nn.sum() if nn.sum() else np.nan
    point_date_mean = float(np.nanmean(av)) if np.isfinite(av).any() else np.nan
    point_med = float(np.nanmedian(md)) if np.isfinite(md).any() else np.nan
    return (mean_draws, date_mean_draws, med_draws, point_mean, point_date_mean,
            point_med, int(nn.sum()), int(np.isfinite(md).sum()))


def _ci(draws: np.ndarray) -> tuple[float, float, int]:
    d = draws[np.isfinite(draws)]
    if d.size == 0:
        return float("nan"), float("nan"), 0
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5)), int(draws.size - d.size)


def single(sub: pd.DataFrame, rcol: str, label: str) -> dict:
    rng = np.random.default_rng(SEED)
    tab = _prep(sub, rcol)
    dates = tab.index
    if len(dates) == 0:
        return {"test": label, "n_fires": 0, "n_dates": 0}
    idx = _draw(len(dates), rng)
    mn, dm, md, pm, pdm, pmd, nf, nd = _stats(tab, dates, idx)
    lo, hi, drop = _ci(mn)
    dlo, dhi, _ = _ci(dm)
    lo2, hi2, _ = _ci(md)
    return {"test": label, "stat": "mean_R", "point": pm, "ci_lo": lo, "ci_hi": hi,
            "n_fires": nf, "n_dates": len(dates), "nan_draws": drop,
            "equal_date_mean": {"stat": "mean_of_per_date_mean_R", "point": pdm,
                                "ci_lo": dlo, "ci_hi": dhi},
            "per_date_median": {"stat": "median_of_per_date_median_R", "point": pmd,
                                "ci_lo": lo2, "ci_hi": hi2}}


def diff(sub_a: pd.DataFrame, sub_b: pd.DataFrame, rcol: str, label: str,
         name_a: str, name_b: str) -> dict:
    """A - B, resampling the UNION of both arms' dates jointly."""
    rng = np.random.default_rng(SEED)
    ta, tb = _prep(sub_a, rcol), _prep(sub_b, rcol)
    dates = ta.index.union(tb.index)
    if len(dates) == 0:
        return {"test": label, "n_fires": 0, "n_dates": 0}
    idx = _draw(len(dates), rng)
    mna, dma, mda, pma, pdma, pmda, nfa, _ = _stats(ta, dates, idx)
    mnb, dmb, mdb, pmb, pdmb, pmdb, nfb, _ = _stats(tb, dates, idx)
    lo, hi, drop = _ci(mna - mnb)
    dlo, dhi, _ = _ci(dma - dmb)
    lo2, hi2, _ = _ci(mda - mdb)
    return {"test": label, "stat": f"mean_R diff ({name_a} - {name_b})",
            "point": pma - pmb, "ci_lo": lo, "ci_hi": hi,
            "n_fires": nfa + nfb, "n_dates": len(dates), "nan_draws": drop,
            f"n_fires_{name_a}": nfa, f"n_fires_{name_b}": nfb,
            f"point_{name_a}": pma, f"point_{name_b}": pmb,
            "date_support_overlap": int(len(ta.index.intersection(tb.index))),
            "equal_date_mean": {"stat": "mean_of_per_date_mean_R diff",
                                "point": pdma - pdmb, "ci_lo": dlo, "ci_hi": dhi},
            "per_date_median": {"stat": "median_of_per_date_median_R diff",
                                "point": pmda - pmdb, "ci_lo": lo2, "ci_hi": hi2}}


def main() -> int:
    df, st = collect()
    # systemic flags, joined exactly as study.main does: SPY state at the last session
    # at-or-before the fire's known_ts.
    sidx = st.index
    kt = pd.DatetimeIndex(df["known_ts"])
    pos = sidx.searchsorted(kt, side="right") - 1
    ok = pos >= 0
    posc = np.clip(pos, 0, len(sidx) - 1)
    for col in ("sysA", "sysAB"):
        df[col] = np.where(ok, st[col].to_numpy()[posc], False)
    print(f"[events] US n={len(df)} blocked={int((df.arm=='blocked').sum())} "
          f"taken={int((df.arm=='taken').sum())} placebo={int((df.arm=='placebo').sum())}",
          flush=True)

    out: dict = {"meta": {"B": B, "seed": SEED, "cluster_unit": "entry_date",
                          "panel": "US", "exit": "(a) stop + 252d time exit",
                          "ci": "percentile 2.5/97.5",
                          "equal_date_weighting": "mean of each date's mean R",
                          "placebo_seed_rule": "20260809 + md5(symbol)[:8] mod 100000",
                          "signal_source_sha256": S.SIGNAL_SOURCE_SHA256,
                          "input_note": "event dicts regenerated via study.events_for_symbol; "
                                        "events_anchor0.parquet carries no a_R column",
                          "held_out_era": "entry_date > 2018-12-31"}, "tests": {}}

    for pname, (rcol, syscol) in PARAMS.items():
        v = df[df.era == "verdict"]
        blk, plc, tkn = (v[v.arm == "blocked"], v[v.arm == "placebo"], v[v.arm == "taken"])
        res = {}

        # 1. H1 registered — non-systemic blocked, and blocked-minus-placebo within non-systemic
        res["H1_nonsystemic_blocked_expectancy"] = single(
            blk[~blk[syscol].astype(bool)], f"R_{rcol}", "H1 non-systemic blocked (held-out)")
        res["H1_nonsystemic_blocked_minus_placebo"] = diff(
            blk[~blk[syscol].astype(bool)], plc[~plc[syscol].astype(bool)], f"R_{rcol}",
            "H1 non-systemic blocked - placebo (held-out)", "blocked", "placebo")

        # 2. H2 registered — within systemic, washout T minus F
        sb = blk[blk[syscol].astype(bool)]
        res["H2_systemic_washT_minus_washF"] = diff(
            sb[sb.washout], sb[~sb.washout], f"R_{rcol}",
            "H2 systemic: washout T - F (held-out)", "washT", "washF")

        # 3. POST-HOC — systemic/washF cell, and sysT minus sysF on all blocked fires
        res["POSTHOC_systemic_washF_expectancy"] = single(
            sb[~sb.washout], f"R_{rcol}", "POST-HOC systemic/washF blocked (held-out)")
        res["POSTHOC_sysT_minus_sysF_all_blocked"] = diff(
            blk[blk[syscol].astype(bool)], blk[~blk[syscol].astype(bool)], f"R_{rcol}",
            "POST-HOC sysT - sysF, all blocked (held-out)", "sysT", "sysF")

        # 4. Pooled full history — blocked minus taken
        pb, pt = df[df.arm == "blocked"], df[df.arm == "taken"]
        res["POOLED_fullhistory_blocked_minus_taken"] = diff(
            pb, pt, f"R_{rcol}", "POOLED full-history blocked - taken", "blocked", "taken")

        out["tests"][pname] = res

    (HERE / "ci_results.json").write_text(json.dumps(out, indent=1, default=str))

    hdr = f"{'test':52s}{'param':10s}{'point':>9s}{'ci_lo':>9s}{'ci_hi':>9s}{'fires':>8s}{'dates':>7s}"
    print("\n" + hdr); print("-" * len(hdr))
    for pname in PARAMS:
        tag = "m0.5" if "0.5" in pname else "m1.0"
        for r in out["tests"][pname].values():
            if not r.get("n_dates"):
                continue
            print(f"{r['test'][:51]:52s}{tag:10s}{r['point']:>9.3f}{r['ci_lo']:>9.3f}"
                  f"{r['ci_hi']:>9.3f}{r['n_fires']:>8d}{r['n_dates']:>7d}")
    print("\nregistered equal-date-weighted versions:")
    for pname in PARAMS:
        tag = "m0.5" if "0.5" in pname else "m1.0"
        for k, r in out["tests"][pname].items():
            if not r.get("n_dates") or "equal_date_mean" not in r:
                continue
            if not k.startswith(("H1", "H2")):
                continue
            p = r["equal_date_mean"]
            print(f"{r['test'][:51]:52s}{tag:10s}{p['point']:>9.3f}{p['ci_lo']:>9.3f}"
                  f"{p['ci_hi']:>9.3f}")
    print("\nper-date-median descriptive versions (tests 1 and 3):")
    for pname in PARAMS:
        tag = "m0.5" if "0.5" in pname else "m1.0"
        for k, r in out["tests"][pname].items():
            if not r.get("n_dates") or "per_date_median" not in r:
                continue
            if not (k.startswith("H1") or k.startswith("POSTHOC")):
                continue
            p = r["per_date_median"]
            print(f"{r['test'][:51]:52s}{tag:10s}{p['point']:>9.3f}{p['ci_lo']:>9.3f}"
                  f"{p['ci_hi']:>9.3f}")
    print(f"\n-> {HERE / 'ci_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
