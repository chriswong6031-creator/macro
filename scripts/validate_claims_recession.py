"""Phase-0 validation: does folding initial jobless claims into the recession_risk
composite (engine/conditions.py) actually improve recession detection vs NBER?

The composite feeds the macro-risk SCORE (sector heat + per-stock ladder), so house
discipline is: validate BEFORE wiring. The honest question is INCREMENTAL value over
the existing legs — and especially over the Sahm leg, which is itself unemployment-
derived and so partly redundant with claims. Claims' edge, if any, is LEAD TIME
(weekly, turns before the unemployment rate moves enough to trip Sahm).

Method (monthly panel, ~1967-2026, ~8 NBER recessions):
  • Replicate the conditions.py 0..1 leg transforms + weights from config.
  • Build base composite (existing legs, renormalized over available) and a
    with-claims composite (+ claims leg at candidate weights).
  • Targets: NBER concurrent, and NBER within next 6 / 12 months (the lead test).
  • Metrics: standalone leg AUCs, claims-vs-Sahm redundancy, ΔAUC (base vs +claims),
    split-half stability (both halves must improve), and threshold lead/false-alarm.
  • Verdict: WIRE (with a conservative weight) only if ΔAUC>0 at the forward horizons
    AND it holds in BOTH split halves AND it does not add false alarms.

CAVEAT: uses stored (latest-revised) series, not ALFRED point-in-time vintages — a
directional Phase-0 read (claims/curve are barely revised; Sahm/NY-Fed prob are). NBER
dates are final. A PIT re-run is the natural Phase-1 follow-up.

Run: .venv/bin/python -m scripts.validate_claims_recession
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sklearn.metrics import roc_auc_score  # noqa: E402

from collectors.fred import FredAdapter  # noqa: E402
from lib import config, store  # noqa: E402

WEIGHTS = config.load()["engine"]["conditions"]["recession"]["weights"]


def _monthly(grp: str, name: str, how: str = "last") -> pd.Series | None:
    df = store.read(grp, name)
    if df is None or df.empty:
        return None
    s = df.iloc[:, 0].copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    r = s.resample("MS")
    return (r.last() if how == "last" else r.mean())


def _usrec() -> pd.Series:
    df = FredAdapter()._fetch_one("USREC", "usrec")
    s = pd.to_numeric(df["usrec"], errors="coerce")
    s.index = pd.to_datetime(s.index)
    return s.sort_index().resample("MS").last()


def _pctile(s: pd.Series, window: int = 120, minp: int = 36) -> pd.Series:
    return s.rolling(window, min_periods=minp).apply(lambda w: (w <= w.iloc[-1]).mean(), raw=False)


def build_panel() -> pd.DataFrame:
    ic4 = _monthly("fred", "IC4WSA")
    sahm = _monthly("fred", "SAHMREALTIME")
    rprob = _monthly("fred", "RECPROUSM156N")
    dgs10 = _monthly("fred", "DGS10")
    dgs2 = _monthly("fred", "DGS2")
    tp = _monthly("fred", "THREEFYTP10")
    ebp_df = store.read("fedboard", "ebp")
    ebp = est = None
    if ebp_df is not None:
        ebp_df = ebp_df.copy(); ebp_df.index = pd.to_datetime(ebp_df.index)
        ebp = ebp_df["ebp"].resample("MS").last()
        est = ebp_df["est_prob"].resample("MS").last() if "est_prob" in ebp_df else None
    usrec = _usrec()

    idx = pd.period_range("1967-01", "2026-05", freq="M").to_timestamp()
    P = pd.DataFrame(index=idx)
    def put(n, s): P[n] = s.reindex(idx) if s is not None else np.nan

    put("ic4", ic4); put("sahm", sahm); put("rprob", rprob)
    put("dgs10", dgs10); put("dgs2", dgs2); put("tp", tp)
    put("ebp", ebp); put("est", est); put("usrec", usrec)
    P["usrec"] = P["usrec"].ffill(limit=1)

    # --- existing leg transforms (mirror engine/conditions.py exactly) ---------
    rc = config.load()["engine"]["conditions"]["recession"]
    P["leg_sahm"] = (P["sahm"] / rc["sahm_full"]).clip(0, 1)
    P["leg_rprob"] = (P["rprob"] / 100.0).clip(0, 1)
    P["leg_ebp_prob"] = P["est"].clip(0, 1)
    curve_tp_adj = (P["dgs10"] - P["dgs2"]) + P["tp"]
    lo, full = rc["curve_invert_level"], rc["curve_full_invert"]
    P["leg_curve"] = ((lo - curve_tp_adj) / (lo - full)).clip(0, 1)
    P["leg_ebp_level"] = _pctile(P["ebp"]).clip(0, 1)

    # --- candidate CLAIMS legs (0..1, recession-ward) -------------------------
    # PRIMARY: 12m %-change of the 4wk-MA level (claims surge in/before recessions)
    P["claims_yoy"] = P["ic4"].pct_change(12)
    P["leg_claims_yoy"] = (P["claims_yoy"] / 0.40).clip(0, 1)        # +40% y/y -> full
    # ROBUSTNESS: Sahm-analog on claims = rise off the trailing-12m low
    P["leg_claims_trough"] = ((P["ic4"] / P["ic4"].rolling(12, min_periods=6).min()) - 1.0).div(0.40).clip(0, 1)
    return P


EXIST = {"sahm": "leg_sahm", "recession_prob": "leg_rprob", "ebp_prob": "leg_ebp_prob",
         "curve": "leg_curve", "ebp_level": "leg_ebp_level"}


def composite(P: pd.DataFrame, extra: dict | None = None) -> pd.Series:
    """Weighted mean over AVAILABLE legs (renormalized) * 100 — the engine's rule."""
    legs = {k: (P[col], WEIGHTS[k]) for k, col in EXIST.items()}
    if extra:
        legs.update(extra)
    num = sum(s.fillna(0) * w for s, w in legs.values())
    den = sum(s.notna().astype(float) * w for s, w in legs.values())
    return 100.0 * num / den.replace(0, np.nan)


def fwd(y: pd.Series, k: int) -> pd.Series:
    """NBER recession within the next k months (k=0 -> concurrent)."""
    if k == 0:
        return y
    return pd.concat([y.shift(-i) for i in range(0, k + 1)], axis=1).max(axis=1)


def auc(score: pd.Series, y: pd.Series) -> tuple[float, int]:
    d = pd.concat([score, y], axis=1).dropna()
    d = d[d.iloc[:, 1].isin([0, 1])]
    if d.iloc[:, 1].nunique() < 2 or len(d) < 30:
        return float("nan"), len(d)
    return roc_auc_score(d.iloc[:, 1], d.iloc[:, 0]), len(d)


def threshold_episodes(score: pd.Series, y: pd.Series, thr: float):
    """Lead months to each NBER onset + false-alarm episode count at `thr`."""
    s = score.dropna(); y = y.reindex(s.index).fillna(0)
    onsets = list(y.index[(y.diff() == 1)])
    fired = s >= thr
    leads = []
    for o in onsets:
        prior = fired[(fired.index <= o) & (fired.index >= o - pd.DateOffset(months=24))]
        first = prior[prior].index.min() if prior.any() else None
        leads.append(None if first is None else round((o - first).days / 30.44, 1))
    # false-alarm episodes: contiguous fired runs with NO NBER month within +/-12m
    grp = (fired != fired.shift()).cumsum()
    fp = 0
    for _, run in fired[fired].groupby(grp[fired]):
        a, b = run.index.min(), run.index.max()
        win = y[(y.index >= a - pd.DateOffset(months=12)) & (y.index <= b + pd.DateOffset(months=12))]
        if win.sum() == 0:
            fp += 1
    return leads, fp, len(onsets)


def main() -> int:
    P = build_panel()
    print(f"panel {P.index.min().date()}..{P.index.max().date()}  "
          f"NBER recession months: {int(P['usrec'].sum())}  "
          f"onsets: {int((P['usrec'].diff()==1).sum())}\n")

    horizons = {"concurrent": 0, "within 6m": 6, "within 12m": 12}
    ys = {h: fwd(P["usrec"], k) for h, k in horizons.items()}

    print("=== standalone leg AUC (recession discrimination) ===")
    print(f"{'leg':<16}" + "".join(f"{h:>14}" for h in horizons))
    legs_show = list(EXIST.values()) + ["leg_claims_yoy", "leg_claims_trough"]
    for leg in legs_show:
        row = "".join(f"{auc(P[leg], ys[h])[0]:>14.3f}" for h in horizons)
        print(f"{leg:<16}{row}")

    r = P[["leg_claims_yoy", "leg_sahm"]].dropna()
    print(f"\nclaims_yoy vs sahm leg correlation: {r.corr().iloc[0,1]:.2f}  (redundancy check)")

    print("\n=== composite AUC: base vs +claims  (PRIMARY claims_yoy) ===")
    base = composite(P)
    print(f"{'variant':<26}" + "".join(f"{h:>14}" for h in horizons))
    print(f"{'base (5 legs)':<26}" + "".join(f"{auc(base, ys[h])[0]:>14.3f}" for h in horizons))
    cand = {}
    for w in (0.5, 1.0):
        wc = composite(P, {"claims": (P["leg_claims_yoy"], w)})
        cand[w] = wc
        print(f"{'+claims (w='+str(w)+')':<26}" + "".join(f"{auc(wc, ys[h])[0]:>14.3f}" for h in horizons))

    print("\n=== ΔAUC (with-claims minus base) — positive = improvement ===")
    print(f"{'weight':<10}" + "".join(f"{h:>14}" for h in horizons))
    for w, wc in cand.items():
        print(f"{w:<10}" + "".join(f"{auc(wc,ys[h])[0]-auc(base,ys[h])[0]:>+14.3f}" for h in horizons))

    print("\n=== split-half ΔAUC (within 6m) — must hold in BOTH halves (w=0.5) ===")
    mid = P.index[len(P)//2]
    for label, mask in (("early " + str(P.index.min().year) + "-" + str(mid.year), P.index < mid),
                        ("late  " + str(mid.year) + "-" + str(P.index.max().year), P.index >= mid)):
        yb = ys["within 6m"][mask]
        db = auc(base[mask], yb)[0]; dc = auc(cand[0.5][mask], yb)[0]
        n_onsets = int((P["usrec"][mask].diff() == 1).sum())
        print(f"  {label}: base {db:.3f} -> +claims {dc:.3f}  (Δ{dc-db:+.3f}, onsets={n_onsets})")

    print("\n=== threshold lead (months) + false-alarm episodes  (high=55, w=0.5) ===")
    lb, fpb, n = threshold_episodes(base, P["usrec"], 55)
    lc, fpc, _ = threshold_episodes(cand[0.5], P["usrec"], 55)
    print(f"  base    : leads {[x for x in lb if x is not None]}  median "
          f"{np.nanmedian([x for x in lb if x is not None]):.1f}  false-alarms {fpb}")
    print(f"  +claims : leads {[x for x in lc if x is not None]}  median "
          f"{np.nanmedian([x for x in lc if x is not None]):.1f}  false-alarms {fpc}")

    # --- verdict --------------------------------------------------------------
    d6 = auc(cand[0.5], ys["within 6m"])[0] - auc(base, ys["within 6m"])[0]
    d12 = auc(cand[0.5], ys["within 12m"])[0] - auc(base, ys["within 12m"])[0]
    e_mask, l_mask = P.index < mid, P.index >= mid
    de = auc(cand[0.5][e_mask], ys["within 6m"][e_mask])[0] - auc(base[e_mask], ys["within 6m"][e_mask])[0]
    dl = auc(cand[0.5][l_mask], ys["within 6m"][l_mask])[0] - auc(base[l_mask], ys["within 6m"][l_mask])[0]
    both_halves = (de > 0) and (dl > 0)
    no_new_fp = fpc <= fpb
    wire = (d6 > 0.005 and d12 > 0) and both_halves and no_new_fp
    print("\n" + "=" * 60)
    print(f"VERDICT: {'WIRE claims leg (w=0.5)' if wire else 'DO NOT WIRE (insufficient incremental value)'}")
    print(f"  fwd6 ΔAUC {d6:+.3f} | fwd12 ΔAUC {d12:+.3f} | "
          f"split-half both-positive {both_halves} (early {de:+.3f}, late {dl:+.3f}) | "
          f"no new false-alarms {no_new_fp} ({fpb}->{fpc})")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
