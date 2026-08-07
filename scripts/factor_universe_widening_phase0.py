#!/usr/bin/env python3
"""Phase-0: what does widening the FACTOR price universe to the Russell 2000 cost?

`engine.equity_factors._closes()` reads `_UNIVERSE_GROUPS["broad"]` = the three S&P
groups only, so a Russell-2000-only name gets no price -> no mktcap -> no factor row ->
no archetype label. Widening that group is the obvious unblock for the Signal Episode
Atlas cohort gap (#4677/#4688) and for a faithful Quant Lab QV recreation (masterplan
§5: Fintel's QV is a small-cap discovery model).

It is not a config bump. Every factor leg is a WINSORIZED CROSS-SECTIONAL z, so the
population defines mu/sd; and `composite_rank` is a BOARD TIEBREAK
(scripts/build_stock_library.py, scripts/build_site.py) -> rank AUTHORITY, which under
the CLAUDE.md epistemics law needs the promotion gauntlet, not a free display-tier ship.

This harness measures the cost instead of asserting it. Five stages:

  1. universe    who the widening actually admits, on the committed data
  2. coverage    per-leg EDGAR reach on R2000-only filers vs the S&P 1500 (SEC frames)
  3. churn       POOLED widening: what moves for names already on the page
  4. equal-N     cap-ordered vs random removal at identical N — the
                 [[universe-widening-rebase-is-cohort-direction-not-count]] decomposition
  5. frozen      FROZEN-REFERENCE widening (Option D): score R2000 against the incumbent
                 mu/sd. Zero incumbent churn by construction — is it usable?

PRICES. Russell closes live in `data/russell_breadth/_closes_cache.parquet`, which is
GITIGNORED (an actions/cache artifact, restored only by daily.yml / closing-bell.yml and
never by ci.yml) and absent on a cold clone — that is charter constraint #2, and the
reason this harness falls back to the COMMITTED high/low caches' midpoint. The proxy is
validated against real closes on the S&P 1500 cohort every run and its error is printed;
it is a measurement device, never a shipping path.

Deterministic apart from the SEC fetch: fixed seed, no wall-clock. Frames are cached to
--cache-dir (default: a tmp dir) and never written into data/.

Usage:  python3 scripts/factor_universe_widening_phase0.py [--stage all] [--fy 2024]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from lib import config  # noqa: E402

SEED = 20260806
GROUPS_BROAD = ("breadth", "smallcap_breadth", "midcap_breadth")
FLOW_TAGS = {
    "ni": "NetIncomeLoss",
    "gross_profit": "GrossProfit",
    "cfo": "NetCashProvidedByUsedInOperatingActivities",
    "dividends": "PaymentsOfDividendsCommonStock",
    "repurchases": "PaymentsForRepurchaseOfCommonStock",
    "op_income": "OperatingIncomeLoss",
    "interest_exp": "InterestExpense",
}
BAL_TAGS = {"assets": "Assets", "equity": "StockholdersEquity",
            "debt_lt": "LongTermDebtNoncurrent"}
# engine parity: Revenues preferred, RFCWCEAT the documented fallback
REV_TAGS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")


# ----------------------------------------------------------------- SEC frames
class Frames:
    """One keyless call per us-gaap concept returns EVERY filer for a period."""

    def __init__(self, cache_dir: Path):
        self.cfg = config.load()["edgar"]
        self.dir = cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.headers = {"User-Agent": self.cfg["user_agent"],
                        "Accept-Encoding": "gzip, deflate"}

    def _get(self, url: str, key: str) -> dict:
        p = self.dir / f"{key}.json"
        if p.exists():
            return json.loads(p.read_text())
        import requests
        for attempt in range(3):
            try:
                r = requests.get(url, headers=self.headers, timeout=60)
                if r.status_code == 404:
                    p.write_text("{}")
                    return {}
                r.raise_for_status()
                d = r.json()
                p.write_text(json.dumps(d))
                time.sleep(0.4)          # SEC fair-access pacing
                return d
            except Exception as e:  # noqa: BLE001 — tolerate a per-frame failure
                if attempt == 2:
                    print(f"::warning title=frames fetch failed::{key}: {e}", flush=True)
                    return {}
                time.sleep(2 * (attempt + 1))
        return {}

    def flow(self, concept: str, fy: int) -> dict[int, float]:
        d = self._get(f"{self.cfg['base_url']}/{concept}/USD/CY{fy}.json", f"{concept}_CY{fy}")
        return {int(x["cik"]): float(x["val"]) for x in d.get("data", [])
                if x.get("val") is not None}

    def balance(self, concept: str, fy: int) -> dict[int, float]:
        """Most recent instantaneous value per CIK across the 4 quarter frames —
        engine parity with collectors.edgar._latest_balance (a Sep-FY filer lands
        in Q3I, a Dec-FY filer in Q4I)."""
        out: dict[int, float] = {}
        for q in ("Q1I", "Q2I", "Q3I", "Q4I"):
            d = self._get(f"{self.cfg['base_url']}/{concept}/USD/CY{fy}{q}.json",
                          f"{concept}_CY{fy}{q}")
            for x in d.get("data", []):
                if x.get("val") is not None:
                    out[int(x["cik"])] = float(x["val"])
        return out

    def shares(self, fy: int) -> dict[int, float]:
        out: dict[int, float] = {}
        for q in ("Q1I", "Q2I", "Q3I", "Q4I"):
            d = self._get(f"{self.cfg['shares_url']}/EntityCommonStockSharesOutstanding"
                          f"/shares/CY{fy}{q}.json", f"dei_shares_CY{fy}{q}")
            for x in d.get("data", []):
                if x.get("val"):
                    out[int(x["cik"])] = float(x["val"])
        return out

    def ticker_cik(self) -> dict[str, int]:
        d = self._get(self.cfg["tickers_url"], "company_tickers")
        rows = d.values() if isinstance(d, dict) else d
        return {str(v["ticker"]).upper(): int(v["cik_str"]) for v in rows}


# ------------------------------------------------------------------ universes
def _read(group: str, name: str) -> pd.DataFrame | None:
    p = config.data_dir() / group / f"{name}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def load_panels() -> dict:
    """Committed price panels. Russell closes are gitignored, so the R2000 leg uses the
    COMMITTED high/low midpoint (validated against real closes on the S&P 1500)."""
    closes, mids = [], []
    for g in GROUPS_BROAD:
        c = _read(g, "_closes_cache")
        if c is not None:
            closes.append(c)
        hi, lo = _read(g, "_high_cache"), _read(g, "_low_cache")
        if hi is not None and lo is not None:
            mids.append((hi + lo) / 2.0)
    broad = pd.concat(closes, axis=1, sort=True)
    broad = broad.loc[:, ~broad.columns.duplicated()].sort_index()
    broad_mid = pd.concat(mids, axis=1, sort=True)
    broad_mid = broad_mid.loc[:, ~broad_mid.columns.duplicated()].sort_index()

    rhi, rlo = _read("russell_breadth", "_high_cache"), _read("russell_breadth", "_low_cache")
    rus_mid = ((rhi + rlo) / 2.0).sort_index() if rhi is not None and rlo is not None \
        else pd.DataFrame()
    rus_closes = _read("russell_breadth", "_closes_cache")   # normally ABSENT — that is the point

    broad_names = set(broad.columns)
    for g in GROUPS_BROAD:
        cons = _read(g, "constituents")
        if cons is not None:
            broad_names |= set(cons.index.astype(str))
    rcons = _read("russell_breadth", "constituents")
    rus_names = set(rcons.index.astype(str)) if rcons is not None else set()
    return {"broad": broad, "broad_mid": broad_mid, "rus_mid": rus_mid,
            "rus_closes": rus_closes, "broad_names": broad_names,
            "rus_only": sorted(rus_names - broad_names)}


def validate_proxy(P: dict) -> dict:
    """The midpoint stands in for absent Russell closes. Measure its error where BOTH
    exist (the S&P 1500) so the churn numbers carry their own error bar."""
    cols = [c for c in P["broad"].columns if c in P["broad_mid"].columns]
    cb = P["broad"][cols].ffill().iloc[-1]
    mb = P["broad_mid"][cols].reindex(P["broad"].index).ffill().iloc[-1]
    err = ((mb - cb) / cb.replace(0, np.nan)).dropna()
    rb = P["broad"][cols].pct_change(fill_method=None).tail(252)
    rm = P["broad_mid"][cols].reindex(P["broad"].index).pct_change(fill_method=None).tail(252)
    vb, vm = rb.std() * np.sqrt(252), rm.std() * np.sqrt(252)
    vr = (vm / vb.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).dropna()
    out = {"n": int(len(err)), "px_abs_err_p50": float(err.abs().median()),
           "px_abs_err_p95": float(err.abs().quantile(.95)),
           "px_spearman": float(cb.corr(mb, method="spearman")),
           "vol_ratio_p50": float(vr.median()),
           "vol_spearman": float(vb.corr(vm, method="spearman"))}
    print("\n[proxy] midpoint vs real close, S&P 1500 cohort (n=%d)" % out["n"])
    print(f"        last price |err| p50 {out['px_abs_err_p50']*100:.3f}%  "
          f"p95 {out['px_abs_err_p95']*100:.3f}%  Spearman {out['px_spearman']:.5f}")
    print(f"        ann vol ratio p50 {out['vol_ratio_p50']:.3f}  "
          f"Spearman {out['vol_spearman']:.5f}  "
          "(midpoint SMOOTHS -> understates vol; low_vol reads are indicative only)")
    return out


# --------------------------------------------------------------- factor legs
def winsor_z(s: pd.Series, cap: float, ref: pd.Series | None = None) -> pd.Series:
    """engine.equity_factors._winsor_z. `ref` freezes mu/sd on another population
    (Option D) — the default ref=None reproduces the shipped pooled behaviour."""
    s = pd.Series(s).replace([np.inf, -np.inf], np.nan)
    base = s if ref is None else pd.Series(ref).replace([np.inf, -np.inf], np.nan)
    mu, sd = base.mean(), base.std()
    if not sd or np.isnan(sd):
        return pd.Series(np.nan, index=s.index)
    return ((s - mu) / sd).clip(-cap, cap)


def ratios(d: pd.DataFrame) -> dict[str, pd.Series]:
    mc = d["mktcap"].where(d["mktcap"] > 0)
    avg_assets = (d["assets"] + d["assets_prior"]) / 2.0
    pay = (d["dividends"].fillna(0) + d["repurchases"].fillna(0)) / mc
    pay[d["dividends"].isna() & d["repurchases"].isna()] = np.nan   # engine parity
    return {"ey": d["ni"] / mc, "bp": d["equity"] / mc, "sp": d["revenue"] / mc,
            "cfoy": d["cfo"] / mc, "gp": d["gross_profit"] / d["assets"],
            "roe": d["ni"] / d["equity"].where(d["equity"] > 0),
            "accr": (d["ni"] - d["cfo"]) / avg_assets, "lev": d["debt_lt"] / d["assets"],
            "ag": d["assets"] / d["assets_prior"] - 1.0, "pay": pay, "vol": d["vol"]}


def legs(d: pd.DataFrame, cap: float, composite: list[str],
         ref: pd.DataFrame | None = None) -> pd.DataFrame:
    """Reproduces engine.equity_factors' leg block. `ref` (a DataFrame in the same
    shape as `d`) freezes every mu/sd on that population — Option D."""
    r = ratios(d)
    rr = ratios(ref) if ref is not None else None

    def z(key):
        return winsor_z(r[key], cap, None if rr is None else rr[key])

    raw = pd.DataFrame(index=d.index)
    raw["value"] = pd.concat([z("ey"), z("bp"), z("sp"), z("cfoy")], axis=1).mean(axis=1)
    raw["profitability"] = z("gp")
    raw["quality"] = pd.concat([z("roe"), -z("accr"), -z("lev")], axis=1).mean(axis=1)
    raw["investment"] = -z("ag")
    raw["payout"] = z("pay")
    raw["low_vol"] = -z("vol")

    if rr is None:
        fac = pd.DataFrame({c: winsor_z(raw[c], cap) for c in raw.columns})
    else:                                    # second pass also frozen on the reference
        base = pd.DataFrame(index=ref.index)   # the reference cohort's OWN raw legs
        base["value"] = pd.concat([winsor_z(rr[k], cap, rr[k]) for k in
                                   ("ey", "bp", "sp", "cfoy")], axis=1).mean(axis=1)
        base["profitability"] = winsor_z(rr["gp"], cap, rr["gp"])
        base["quality"] = pd.concat([winsor_z(rr["roe"], cap, rr["roe"]),
                                     -winsor_z(rr["accr"], cap, rr["accr"]),
                                     -winsor_z(rr["lev"], cap, rr["lev"])], axis=1).mean(axis=1)
        base["investment"] = -winsor_z(rr["ag"], cap, rr["ag"])
        base["payout"] = winsor_z(rr["pay"], cap, rr["pay"])
        base["low_vol"] = -winsor_z(rr["vol"], cap, rr["vol"])
        fac = pd.DataFrame({c: winsor_z(raw[c], cap, base[c]) for c in raw.columns})

    cl = [c for c in composite if c in fac.columns]
    avail = fac[cl].notna()
    comp = fac[cl].where(avail).mean(axis=1)
    comp[avail.sum(axis=1) < 3] = np.nan            # engine parity: >=3 legs
    fac["composite"] = comp
    return fac


def cross_section(tickers, closes, t2c, cols) -> pd.DataFrame:
    ck = {t: t2c[t] for t in tickers if t in t2c and t in closes.columns}
    idx = sorted(ck)
    px = closes[idx].ffill().iloc[-1]
    vol = closes[idx].pct_change(fill_method=None).tail(252).std() * np.sqrt(252)
    d = pd.DataFrame(index=idx)
    for k, m in cols.items():
        d[k] = [m.get(ck[t], np.nan) for t in idx]
    d["price"] = px.reindex(idx)
    d["vol"] = vol.reindex(idx)
    d = d[d["price"].notna() & d["shares"].notna()]
    d["mktcap"] = d["price"] * d["shares"]
    return d


# ----------------------------------------------------------------- the stages
def stage_universe(P: dict) -> None:
    print("\n=== 1. universe — who does widening _closes() admit? ===")
    fund = _read("edgar", "fundamentals")
    panel = _read("edgar", "fundamentals_panel")
    bc = set(P["broad"].columns)
    rc = set(P["rus_mid"].columns)
    print(f"  broad close columns (S&P 1500)  : {len(bc)}")
    print(f"  russell price columns           : {len(rc)}  ({len(rc - bc)} russell-only)")
    print(f"  russell _closes_cache.parquet   : "
          f"{'present' if P['rus_closes'] is not None else 'ABSENT (gitignored CI artifact)'}")
    if fund is not None:
        fi = set(fund.index.astype(str))
        print(f"  fundamentals.parquet names      : {len(fi)}")
        print(f"    in broad price panel          : {len(fi & bc)}")
        print(f"    russell-only (admitted today) : {len(fi - bc & rc)}")
    if panel is not None:
        pt = set(panel["ticker"].astype(str))
        print(f"  multi-fy panel tickers          : {len(pt)}  "
              f"({len(pt & rc - bc)} russell-only)")


def stage_coverage(P: dict, F: Frames, fy: int) -> None:
    print(f"\n=== 2. coverage — per-leg EDGAR reach, R2000-only vs S&P 1500 (FY{fy}) ===")
    t2c = F.ticker_cik()
    cb = {t2c[t] for t in P["broad_names"] if t in t2c}
    cr = {t2c[t] for t in P["rus_only"] if t in t2c}
    print(f"  S&P 1500 union {len(P['broad_names'])} tickers -> {len(cb)} CIKs; "
          f"R2000-only {len(P['rus_only'])} -> {len(cr)} CIKs")
    print(f"  {'leg':14s} {'concept':50s} {'S&P1500':>9s} {'R2000-only':>11s}")
    for leg, concept in {**FLOW_TAGS, **BAL_TAGS}.items():
        ciks = set((F.balance if leg in BAL_TAGS else F.flow)(concept, fy))
        a, b = len(ciks & cb) / max(len(cb), 1), len(ciks & cr) / max(len(cr), 1)
        flag = "  <-- HALVES" if b < a * 0.6 else ""
        print(f"  {leg:14s} {concept:50s} {a*100:8.1f}% {b*100:10.1f}%{flag}")


def _fund_cols(F: Frames, fy: int) -> dict:
    cols = {k: F.flow(c, fy) for k, c in FLOW_TAGS.items() if k != "revenue"}
    r1, r2 = F.flow(REV_TAGS[0], fy), F.flow(REV_TAGS[1], fy)
    cols["revenue"] = {**r2, **r1}
    cols.update({k: F.balance(c, fy) for k, c in BAL_TAGS.items()})
    cols["assets_prior"] = F.balance("Assets", fy - 1)
    cols["ni_prior"] = F.flow("NetIncomeLoss", fy - 1)
    cols["shares"] = F.shares(fy)
    return cols


def _universes(P: dict, F: Frames, fy: int):
    fcfg = config.load()["edgar"]["factors"]
    cap, comp = fcfg["winsor_z"], fcfg["composite"]
    t2c = F.ticker_cik()
    cols = _fund_cols(F, fy)
    dA = cross_section(list(P["broad"].columns), P["broad"], t2c, cols)
    rus = [t for t in P["rus_mid"].columns if t in set(P["rus_only"])]
    dR = cross_section(rus, P["rus_mid"], t2c, cols)
    dR = dR.loc[[i for i in dR.index if i not in dA.index]]
    return cap, comp, dA, dR


def stage_churn(P: dict, F: Frames, fy: int) -> None:
    print("\n=== 3. churn — POOLED widening, what moves for names already on the page ===")
    cap, comp, dA, dR = _universes(P, F, fy)
    dB = pd.concat([dA, dR])
    facA, facB = legs(dA, cap, comp), legs(dB, cap, comp)
    print(f"  A (S&P 1500)      n={len(facA)}")
    print(f"  B (+R2000-only)   n={len(facB)}  ({len(facB)-len(facA):+d}, "
          f"{100*(len(facB)/len(facA)-1):+.1f}%)")
    both = facA.index.intersection(facB.index)
    print(f"\n  {'leg':16s} {'sd A':>7s} {'sd B':>7s} {'Spearman':>9s}   (within the SAME names)")
    for c in [x for x in comp if x in facA.columns] + ["composite"]:
        a, b = facA.loc[both, c], facB.loc[both, c]
        m = a.notna() & b.notna()
        print(f"  {c:16s} {a[m].std():7.3f} {b[m].std():7.3f} "
              f"{a[m].corr(b[m], method='spearman'):9.5f}")
    ca, cb = facA["composite"].dropna(), facB["composite"].dropna()
    sh = ca.index.intersection(cb.index)
    pa, pb = ca.rank(pct=True), cb.rank(pct=True)
    da = pd.qcut(ca.rank(method="first"), 10, labels=False)
    db = pd.qcut(cb.rank(method="first"), 10, labels=False)
    print(f"\n  displayed percentile |delta| p50 {(pb.loc[sh]-pa.loc[sh]).abs().median()*100:.2f}pp"
          f"  p95 {(pb.loc[sh]-pa.loc[sh]).abs().quantile(.95)*100:.2f}pp")
    print(f"  changed decile      {(da.loc[sh]!=db.loc[sh]).sum()} of {len(sh)} "
          f"({100*(da.loc[sh]!=db.loc[sh]).mean():.1f}%)")
    for k in (10, 20, 50):
        surv = len(set(ca.nlargest(k).index) & set(cb.nlargest(k).index))
        new = len([t for t in cb.nlargest(k).index if t not in facA.index])
        print(f"  composite top-{k:<3d} survive {surv:2d}/{k}   new R2000 names {new:2d}")


def stage_equaln(P: dict, F: Frames, fy: int, draws: int = 20) -> None:
    print("\n=== 4. equal-N — is the churn a COUNT effect or a COHORT-DIRECTION effect? ===")
    cap, comp, dA, dR = _universes(P, F, fy)
    dB = pd.concat([dA, dR])
    facB = legs(dB, cap, comp)
    k = len(dR)
    keep_cap = dB["mktcap"].nlargest(len(dB) - k).index
    facCap = legs(dB.loc[keep_cap], cap, comp)

    def compare(fr):
        sh = fr.index.intersection(facB.index)
        a, b = facB.loc[sh, "composite"], fr.loc[sh, "composite"]
        m = a.notna() & b.notna()
        ta = set(facB["composite"].nlargest(50).index) & set(sh)
        tb = set(fr["composite"].nlargest(50).index) & set(sh)
        return ((b[m] - a[m]).median(), a[m].corr(b[m], method="spearman"),
                len(ta & tb) / max(len(ta | tb), 1))

    cs, csp, cj = compare(facCap)
    rng = np.random.default_rng(SEED)
    rs = [compare(legs(dB.loc[pd.Index(rng.choice(dB.index.values, len(dB) - k,
                                                  replace=False))], cap, comp))
          for _ in range(draws)]
    print(f"  removing k={k} from n={len(dB)}")
    print(f"  (a) CAP-ORDERED  shift {cs:+.4f}  Spearman {csp:.4f}  top-50 Jaccard {cj:.3f}")
    print(f"  (b) RANDOM x{draws:<3d}  shift {np.median([x[0] for x in rs]):+.4f}  "
          f"Spearman {np.median([x[1] for x in rs]):.4f}  "
          f"top-50 Jaccard {np.median([x[2] for x in rs]):.3f}")
    print(f"\n  ordering loss (1-Spearman): cap-ordered {1-csp:.4f} vs random "
          f"{1-np.median([x[1] for x in rs]):.4f}  "
          f"-> {(1-csp)/max(1-np.median([x[1] for x in rs]),1e-9):.1f}x at IDENTICAL N")


def stage_frozen(P: dict, F: Frames, fy: int) -> None:
    print("\n=== 5. frozen reference (Option D) — R2000 scored on the incumbent mu/sd ===")
    cap, comp, dA, dR = _universes(P, F, fy)
    facA = legs(dA, cap, comp)
    facR = legs(dR, cap, comp, ref=dA)
    print("  incumbent z's are UNCHANGED by construction (mu/sd never see the R2000 cohort)")
    print(f"  {'leg':16s} {'S&P1500 p50':>12s} {'R2000 p50':>11s} {'R2000 p10':>10s} "
          f"{'R2000 p90':>10s} {'clip%':>7s}")
    for c in [x for x in comp if x in facA.columns]:
        b = facR[c].dropna()
        if b.empty:
            continue
        print(f"  {c:16s} {facA[c].median():12.3f} {b.median():11.3f} {b.quantile(.1):10.3f} "
              f"{b.quantile(.9):10.3f} {(b.abs()>=cap-1e-9).mean()*100:6.1f}%")
    nl = facR[[c for c in comp if c in facR.columns]].notna().sum(axis=1)
    print(f"\n  R2000 names with >=3 scored legs: {100*(nl>=3).mean():.1f}% "
          f"-> ~{int((nl>=3).sum())} newly archetype-labelable names")
    for nm, expr_r, expr_a in (
            ("quality_compounder q>=0.5", facR["quality"] >= 0.5, facA["quality"] >= 0.5),
            ("dividend_defensive pay>=0.5", facR["payout"] >= 0.5, facA["payout"] >= 0.5),
            ("deep_value         v>=0.75", facR["value"] >= 0.75, facA["value"] >= 0.75)):
        print(f"  gate {nm:30s} S&P1500 {100*expr_a.mean():5.1f}%  R2000 {100*expr_r.mean():5.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="all",
                    choices=["all", "universe", "coverage", "churn", "equaln", "frozen"])
    ap.add_argument("--fy", type=int, default=2024,
                    help="fiscal year for the frames cross-section (default 2024)")
    ap.add_argument("--cache-dir", default=None,
                    help="where to cache SEC frames (default: a tmp dir; never data/)")
    a = ap.parse_args()

    cache = Path(a.cache_dir) if a.cache_dir else \
        Path(tempfile.gettempdir()) / "fuw_frames"
    P = load_panels()
    if P["broad"].empty:
        print("::warning title=factor-universe-widening::no S&P close caches — "
              "run the breadth collectors first", flush=True)
        return 1
    validate_proxy(P)
    F = Frames(cache)

    if a.stage in ("all", "universe"):
        stage_universe(P)
    if a.stage in ("all", "coverage"):
        stage_coverage(P, F, a.fy)
    if a.stage in ("all", "churn"):
        stage_churn(P, F, a.fy)
    if a.stage in ("all", "equaln"):
        stage_equaln(P, F, a.fy)
    if a.stage in ("all", "frozen"):
        stage_frozen(P, F, a.fy)
    print("\nCharter: research/FACTOR_UNIVERSE_WIDENING_CHARTER.md  "
          "(registry row DNR:HOLD-FACTOR-UNIVERSE-WIDENING)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
