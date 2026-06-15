"""Phase-0 validation for the Treasury supply-absorption panel (engine/treasury_supply.py).

That leaf ships DISPLAY-ONLY on the documented reasoning that auction results are
public and digested by the close; this harness is the EMPIRICAL gate its docstring
flags as the prerequisite for any future scoring ("a Phase-0 on the accruing history
would gate any future scoring"). It tests the one proposed predictive thesis: that a
weak coupon auction (low bid-to-cover, low indirect/real-money share, high primary-
dealer takedown) is FOLLOWED by higher yields / a cheaper duration sector.

Decisive question = FORWARD predictive content. Auction results print at 1:01pm ET and
the market reacts in seconds, so the null is "fully priced intraday -> zero forward
edge, display-only." We test that null honestly. (The leaf's absorption_z is the
NEGATIVE of this script's `stress`, so a thesis-positive forward IC here == a negative
forward IC on absorption — the same finding in the opposite sign convention.)

DATA (free, keyless, both reachable from here; FRED is NOT):
  • Auction RESULTS  — TreasuryDirect TA_WS /securities/search (bid-to-cover,
    indirect/direct/dealer accepted $, high yield), nominal coupons only (Note+Bond).
  • Daily par yields — Treasury.gov daily_treasury_yield_curve CSV, by tenor.
  NOTE: the true auction TAIL (stop-out minus when-issued) needs paid WI data and is
  intentionally OMITTED — we validate the demand metrics that ARE free.

SIGNAL (per tenor, CAUSAL expanding-z using only PRIOR auctions of that tenor):
    stress = mean[ -z(bid_to_cover), -z(indirect_share), +z(dealer_share) ]
  higher = weaker demand. Plus a pooled EWMA "demand-regime trend" version.

TARGET: change in the auctioned tenor's par yield over h=1/5/21 business days, both
  ABSOLUTE (Δy) and CURVE-RELATIVE (Δy minus the curve-average Δy = the supply-
  specific cheapening, the actual mechanism). Thesis => IC(stress, Δy) > 0.
  Plus a CONTEMPORANEOUS (auction-day) control: should be significant if the signal
  is real; strong same-day + zero forward == priced-in == display-only.

METRICS: Spearman rank IC + p per (signal × horizon × target × tenor); pooled IC with
  a Newey-West t (overlapping windows); Benjamini-Hochberg FDR across the family;
  split-half stability; a top-vs-bottom-tercile event study in bps.

VERDICT (worth SCORING) requires the headline cell — single-auction stress, h=5d,
  curve-relative — to be thesis-signed, |IC|>=0.05, FDR q<=0.10, AND same-signed in
  both split halves. Otherwise DISPLAY-ONLY.

Run: .venv/bin/python -m scripts.treasury_supply_phase0
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.validation import benjamini_hochberg, newey_west_tstat  # noqa: E402

Y0, Y1 = 2008, 2026
STD_TENORS = [2, 3, 5, 7, 10, 20, 30]
YLD_COL = {2: "2 Yr", 3: "3 Yr", 5: "5 Yr", 7: "7 Yr", 10: "10 Yr", 20: "20 Yr", 30: "30 Yr"}
HORIZONS = [1, 5, 21]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) macro-dashboard/research"}
DATA = Path(__file__).resolve().parent.parent / "data" / "treasury_auctions"
# isolated cache names so a manual phase-0 run never clobbers the live collector's
# data/treasury_auctions/auction_results.parquet (engine/treasury_supply.py reads it)
AUCT_PARQUET = DATA / "_phase0_auctions.parquet"
YLD_PARQUET = DATA / "_phase0_yields.parquet"


# --------------------------------------------------------------------------- #
# fetch (cached to parquet so reruns are instant and the pull is reusable)
# --------------------------------------------------------------------------- #
def _http(url: str, tries: int = 4, timeout: int = 40) -> bytes:
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"GET failed after {tries}: {url[:90]} :: {last}")


def _term_to_tenor(term: str) -> int | None:
    """'9-Year 11-Month' -> 10, '29-Year 10-Month' -> 30, '7-Year' -> 7."""
    if not term:
        return None
    yrs = re.findall(r"(\d+)-Year", term)
    mos = re.findall(r"(\d+)-Month", term)
    dec = (int(yrs[0]) if yrs else 0) + (int(mos[0]) if mos else 0) / 12.0
    if dec <= 0:
        return None
    near = min(STD_TENORS, key=lambda t: abs(t - dec))
    return near if abs(near - dec) <= 1.5 else None


def fetch_auctions() -> pd.DataFrame:
    if AUCT_PARQUET.exists():
        return pd.read_parquet(AUCT_PARQUET)
    base = "https://www.treasurydirect.gov/TA_WS/securities/search"
    rows = []
    for yr in range(Y0, Y1 + 1):
        for typ in ("Note", "Bond"):
            url = f"{base}?startDate={yr}-01-01&endDate={yr}-12-31&type={typ}&format=json"
            try:
                recs = json.loads(_http(url))
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] {yr} {typ}: {e}")
                continue
            for r in recs:
                rows.append({
                    "cusip": r.get("cusip"),
                    "type": r.get("securityType"),
                    "term": r.get("securityTerm"),
                    "auction_date": r.get("auctionDate"),
                    "btc": r.get("bidToCoverRatio"),
                    "indirect": r.get("indirectBidderAccepted"),
                    "direct": r.get("directBidderAccepted"),
                    "dealer": r.get("primaryDealerAccepted"),
                    "accepted": r.get("totalAccepted"),
                    "offering": r.get("offeringAmount"),
                    "high_yield": r.get("highYield"),
                })
            print(f"  pulled {yr} {typ}: {len(recs)} (cum {len(rows)})")
    df = pd.DataFrame(rows)
    num = ["btc", "indirect", "direct", "dealer", "accepted", "offering", "high_yield"]
    for c in num:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["auction_date"] = pd.to_datetime(df["auction_date"]).dt.tz_localize(None).dt.normalize()
    df["tenor"] = df["term"].map(_term_to_tenor)
    df = df.dropna(subset=["tenor", "auction_date", "btc", "accepted"])
    df["tenor"] = df["tenor"].astype(int)
    df = df[df["accepted"] > 0].copy()
    df["indirect_share"] = df["indirect"] / df["accepted"]
    df["dealer_share"] = df["dealer"] / df["accepted"]
    df = (df.dropna(subset=["indirect_share", "dealer_share"])
            .drop_duplicates(["cusip", "auction_date"])
            .sort_values("auction_date").reset_index(drop=True))
    DATA.mkdir(parents=True, exist_ok=True)
    df.to_parquet(AUCT_PARQUET)
    return df


def fetch_yields() -> pd.DataFrame:
    if YLD_PARQUET.exists():
        return pd.read_parquet(YLD_PARQUET)
    base = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
    parts = []
    for yr in range(Y0, Y1 + 1):
        try:
            txt = _http(base.format(y=yr)).decode("utf-8", "replace")
            d = pd.read_csv(io.StringIO(txt))
            parts.append(d)
            print(f"  yields {yr}: {len(d)} rows")
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] yields {yr}: {e}")
    raw = pd.concat(parts, ignore_index=True)
    raw["Date"] = pd.to_datetime(raw["Date"], format="%m/%d/%Y", errors="coerce")
    raw = raw.dropna(subset=["Date"]).set_index("Date").sort_index()
    cols = {YLD_COL[t]: t for t in STD_TENORS if YLD_COL[t] in raw.columns}
    Y = raw[list(cols)].rename(columns=cols).apply(pd.to_numeric, errors="coerce")
    Y = Y[~Y.index.duplicated(keep="last")]
    DATA.mkdir(parents=True, exist_ok=True)
    Y.to_parquet(YLD_PARQUET)
    return Y


# --------------------------------------------------------------------------- #
# panel build
# --------------------------------------------------------------------------- #
def causal_z(g: pd.Series) -> pd.Series:
    """Expanding z using only PRIOR observations (shift(1)); NaN until 12 priors."""
    mu = g.shift(1).expanding(min_periods=12).mean()
    sd = g.shift(1).expanding(min_periods=12).std(ddof=0)
    return (g - mu) / sd.replace(0, np.nan)


def build_panel(A: pd.DataFrame, Y: pd.DataFrame) -> pd.DataFrame:
    A = A.sort_values("auction_date").copy()
    # --- per-tenor causal z + stress ---
    for col in ("btc", "indirect_share", "dealer_share"):
        A[f"z_{col}"] = A.groupby("tenor")[col].transform(causal_z)
    A["stress"] = (-A["z_btc"] - A["z_indirect_share"] + A["z_dealer_share"]) / 3.0
    # pooled demand-regime trend (EWMA of stress across all tenors, by date order) — causal
    A["stress_trend"] = A["stress"].ewm(span=6, min_periods=3).mean()

    # --- forward & contemporaneous par-yield moves (bps) per tenor ---
    dates = Y.index.to_numpy()
    pos = {d: i for i, d in enumerate(Y.index)}
    arr = {t: Y[t].to_numpy() for t in Y.columns}
    n = len(Y)

    def yld_pos(d):  # backward asof -> last trading day <= auction date
        i = pos.get(d)
        if i is not None:
            return i
        j = int(np.searchsorted(dates, np.datetime64(d), side="right")) - 1
        return j if j >= 0 else None

    recs = []
    for _, r in A.iterrows():
        t = int(r["tenor"])
        i = yld_pos(r["auction_date"])
        out = {"idx": r.name}
        if i is None or t not in arr:
            recs.append(out)
            continue
        base = arr[t][i]
        # contemporaneous (auction-day close vs prior close), abs + curve-relative
        if i >= 1 and np.isfinite(base) and np.isfinite(arr[t][i - 1]):
            c_abs = (base - arr[t][i - 1]) * 100.0
            curve = np.nanmean([(arr[k][i] - arr[k][i - 1]) for k in arr if np.isfinite(arr[k][i]) and np.isfinite(arr[k][i - 1])]) * 100.0
            out["c_abs"], out["c_rel"] = c_abs, c_abs - curve
        for h in HORIZONS:
            if i + h < n and np.isfinite(base) and np.isfinite(arr[t][i + h]):
                a_abs = (arr[t][i + h] - base) * 100.0
                curve = np.nanmean([(arr[k][i + h] - arr[k][i]) for k in arr if np.isfinite(arr[k][i]) and np.isfinite(arr[k][i + h])]) * 100.0
                out[f"abs_{h}"], out[f"rel_{h}"] = a_abs, a_abs - curve
        recs.append(out)
    F = pd.DataFrame(recs).set_index("idx")
    return A.join(F)


# --------------------------------------------------------------------------- #
# stats
# --------------------------------------------------------------------------- #
def ic(sig: pd.Series, tgt: pd.Series) -> tuple[float, float, int]:
    d = pd.concat([sig, tgt], axis=1).dropna()
    if len(d) < 20:
        return float("nan"), float("nan"), len(d)
    rho, p = spearmanr(d.iloc[:, 0], d.iloc[:, 1])
    return float(rho), float(p), len(d)


def main() -> int:
    print("Fetching auction results (TreasuryDirect TA_WS) + par yields (Treasury.gov)...")
    A = fetch_auctions()
    Y = fetch_yields()
    print(f"\nauctions: {len(A)}  ({A['auction_date'].min().date()}..{A['auction_date'].max().date()})  "
          f"tenors: {sorted(A['tenor'].unique())}")
    print("by tenor: " + "  ".join(f"{t}Y:{int((A['tenor']==t).sum())}" for t in STD_TENORS))
    print(f"par yields: {len(Y)} days  ({Y.index.min().date()}..{Y.index.max().date()})  cols {list(Y.columns)}")

    P = build_panel(A, Y)
    print(f"events with usable stress z (>=12 priors): {int(P['stress'].notna().sum())}")

    SIGNALS = {"single-auction stress": "stress", "demand-regime trend": "stress_trend"}

    # ---- CONTEMPORANEOUS sanity (is the signal even real?) ----
    print("\n" + "=" * 74)
    print("CONTEMPORANEOUS auction-day reaction (sign check: stress↑ => yield↑, IC>0)")
    print("=" * 74)
    print(f"{'signal':<24}{'target':<14}{'IC':>9}{'p':>9}{'n':>7}")
    for sname, scol in SIGNALS.items():
        for tname, tcol in (("abs Δy", "c_abs"), ("curve-rel Δy", "c_rel")):
            rho, p, nn = ic(P[scol], P[tcol])
            print(f"{sname:<24}{tname:<14}{rho:>9.3f}{p:>9.4f}{nn:>7}")

    # ---- FORWARD predictive IC (pooled across tenors) ----
    print("\n" + "=" * 74)
    print("FORWARD predictive IC, pooled  (thesis: stress↑ => forward yield↑, IC>0)")
    print("  NW t = Newey-West t-stat on per-date IC (overlapping windows)")
    print("=" * 74)
    print(f"{'signal':<24}{'target':<16}{'IC':>8}{'p':>8}{'NWt':>7}{'n':>7}")
    pvals = {}
    headline = None
    for sname, scol in SIGNALS.items():
        for kind, lbl in (("abs", "abs Δy"), ("rel", "curve-rel Δy")):
            for h in HORIZONS:
                tcol = f"{kind}_{h}"
                rho, p, nn = ic(P[scol], P[tcol])
                # per-date IC series for a Newey-West t (cluster overlapping windows by date)
                dd = pd.concat([P["auction_date"], P[scol], P[tcol]], axis=1).dropna()
                dd.columns = ["d", "s", "y"]
                per = dd.groupby("d").apply(
                    lambda g: spearmanr(g["s"], g["y"])[0] if len(g) >= 4 else np.nan,
                    include_groups=False).dropna()
                nwt = newey_west_tstat(per, lags=max(1, h // 2))["t"] if len(per) >= 8 else None
                key = f"{sname} | {lbl} | {h}d"
                pvals[key] = p
                nwts = f"{nwt:>7.2f}" if nwt is not None else f"{'—':>7}"
                print(f"{sname:<24}{lbl+' '+str(h)+'d':<16}{rho:>8.3f}{p:>8.4f}{nwts}{nn:>7}")
                if sname == "single-auction stress" and kind == "rel" and h == 5:
                    headline = (rho, p, nn)

    # ---- FDR across the forward family ----
    print("\n=== Benjamini-Hochberg FDR across the forward family (α=0.10) ===")
    bh = benjamini_hochberg(pvals, alpha=0.10)
    any_survive = False
    for k, v in sorted(bh.items(), key=lambda kv: kv[1]["q"]):
        flag = "REJECT-null(signal!)" if v["reject"] else "—"
        any_survive |= v["reject"]
        print(f"  {k:<46} p={v['p']:.4f} q={v['q']:.4f}  {flag}")

    # ---- per-tenor headline (h=5, curve-relative) — does the long end bite? ----
    print("\n=== per-tenor IC: single-auction stress vs curve-rel Δy(5d) ===")
    print(f"{'tenor':<8}{'IC':>9}{'p':>9}{'n':>7}")
    for t in STD_TENORS:
        sub = P[P["tenor"] == t]
        rho, p, nn = ic(sub["stress"], sub["rel_5"])
        if nn >= 20:
            print(f"{str(t)+'Y':<8}{rho:>9.3f}{p:>9.4f}{nn:>7}")

    # ---- event study: weak (top-tercile stress) vs strong (bottom) auctions ----
    print("\n=== event study: forward curve-rel Δy (bps), weak vs strong auctions ===")
    s = P.dropna(subset=["stress"])
    q1, q2 = s["stress"].quantile([1 / 3, 2 / 3])
    weak, strong = s[s["stress"] >= q2], s[s["stress"] <= q1]
    print(f"{'horizon':<10}{'weak(top⅓)':>12}{'strong(bot⅓)':>14}{'diff':>9}{'t':>8}")
    for h in HORIZONS:
        wv, sv = weak[f"rel_{h}"].dropna(), strong[f"rel_{h}"].dropna()
        diff = wv.mean() - sv.mean()
        sp = np.sqrt(wv.var(ddof=1) / len(wv) + sv.var(ddof=1) / len(sv))
        tt = diff / sp if sp else float("nan")
        print(f"{str(h)+'d':<10}{wv.mean():>12.2f}{sv.mean():>14.2f}{diff:>9.2f}{tt:>8.2f}")

    # ---- split-half stability of the headline cell ----
    mid = P["auction_date"].quantile(0.5)
    e = P[P["auction_date"] < mid]
    l = P[P["auction_date"] >= mid]
    ie = ic(e["stress"], e["rel_5"])
    il = ic(l["stress"], l["rel_5"])
    print(f"\nsplit-half headline IC (single-auction, curve-rel 5d): "
          f"early {ie[0]:+.3f} (n={ie[2]}) | late {il[0]:+.3f} (n={il[2]})")

    # ---- VERDICT ----
    rho, p, nn = headline
    q_head = bh.get("single-auction stress | curve-rel Δy | 5d", {}).get("q", 1.0)
    both_signed = np.sign(ie[0]) == np.sign(il[0]) and np.sign(rho) > 0
    go = (rho >= 0.05) and (q_head <= 0.10) and bool(both_signed)
    print("\n" + "=" * 74)
    print(f"VERDICT: {'SCORE-WORTHY (forward edge survives)' if go else 'DISPLAY-ONLY — no forward predictive edge'}")
    print(f"  headline (single-auction stress, curve-rel Δy 5d): IC {rho:+.3f}  p {p:.4f}  "
          f"FDR-q {q_head:.3f}  n {nn}")
    print(f"  gate: IC≥0.05 [{rho >= 0.05}]  FDR-q≤0.10 [{q_head <= 0.10}]  "
          f"thesis-signed both halves [{both_signed}]  | any forward cell survives FDR [{any_survive}]")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
