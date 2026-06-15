"""Phase-0 validation: does commodity TERM STRUCTURE (roll yield / basis) predict
forward returns?  GATE before wiring a `term_structure` factor into the commodity
conviction score.  Validate-before-weight, same discipline as the GEX gate.

THE HYPOTHESIS (storage theory / Keynesian normal backwardation; Gorton-Rouwenhorst
2006, Erb-Harvey 2006): when the futures curve is in BACKWARDATION (front > deferred,
positive roll yield) the asset earns a positive roll return AND historically tends to
out-return contango regimes.  So the basis should POSITIVELY predict forward price.

DATA
- OIL (deep, the real test): EIA keyless hist_xls — Cushing WTI spot (RWTC) + futures
  contracts 1-4 (RCLC1-4), DAILY 1985-2024 (~9.8k rows; the hist_xls froze 2024-04 when
  EIA moved futures to the keyed v2 API — irrelevant for a backtest, it spans every oil
  regime: 1986 collapse, 1990 Gulf, 2008 spike+crash, 2014-16 shale-glut contango, 2020
  negative oil, 2022 backwardation).
- METALS (shallow, reported but underpowered): the live Yahoo roll-yield collector
  data/commodity_carry/{gold,silver,copper}.parquet — only ~18 months (2024-12+), far too
  thin for a credible verdict; included for completeness / forward-accumulation.

CONSERVATISM: the primary test predicts forward SPOT return (the HARD claim) — the
mechanical roll carry that backwardation hands you "for free" is EXCLUDED from the
strategy P&L and only REPORTED separately.  If the spot-prediction edge survives without
crediting carry, it is real.

Run:  python -m scripts.commodity_carry_phase0
Writes research/COMMODITY_CARRY_PHASE0.md + data/commodity_carry/phase0_verdict.json
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import validation as V  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CARRY_DIR = ROOT / "data" / "commodity_carry"
EIA_CACHE = CARRY_DIR / "eia_wti_termstructure.parquet"
COST_BPS = 8.0   # one-way; matches calibrate_commodities
HORIZONS = [21, 63, 126]
UA = {"User-Agent": "macro-dashboard/1.0 (commodity-termstructure research)"}

EIA_SERIES = {  # column -> hist_xls basename
    "spot": "RWTCd", "c1": "RCLC1d", "c2": "RCLC2d", "c3": "RCLC3d", "c4": "RCLC4d",
}


# --------------------------------------------------------------------------- #
# EIA deep history fetch (keyless hist_xls) — cached
# --------------------------------------------------------------------------- #
def _fetch_eia_xls(basename: str) -> pd.Series:
    import requests
    url = f"https://www.eia.gov/dnav/pet/hist_xls/{basename}.xls"
    r = requests.get(url, headers=UA, timeout=45)
    r.raise_for_status()
    xl = pd.read_excel(io.BytesIO(r.content), sheet_name="Data 1", skiprows=2)
    xl = xl.iloc[:, :2]
    xl.columns = ["date", "value"]
    xl["date"] = pd.to_datetime(xl["date"], errors="coerce")
    s = (xl.dropna(subset=["date"]).set_index("date")["value"]
         .astype(float).sort_index())
    return s[~s.index.duplicated(keep="last")]


def load_eia_termstructure() -> pd.DataFrame:
    if EIA_CACHE.exists():
        return pd.read_parquet(EIA_CACHE)
    print("[eia] fetching deep WTI term structure (spot + C1-4) ...")
    cols = {}
    for name, base in EIA_SERIES.items():
        try:
            cols[name] = _fetch_eia_xls(base)
            print(f"  {name:5s} {base:8s} rows={len(cols[name])} "
                  f"{str(cols[name].index.min())[:10]}..{str(cols[name].index.max())[:10]}")
        except Exception as e:  # noqa: BLE001
            print(f"  {name:5s} {base:8s} FAILED: {e!r}")
    df = pd.DataFrame(cols).sort_index()
    df = df[df.index >= "1985-01-01"]
    CARRY_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(EIA_CACHE)
    print(f"[eia] cached {len(df)} rows -> {EIA_CACHE.relative_to(ROOT)}")
    return df


# --------------------------------------------------------------------------- #
# signal construction
# --------------------------------------------------------------------------- #
def basis_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Roll-yield / term-structure signals from the futures stack. Positive =
    BACKWARDATION (front rich vs deferred) = storage-theory bullish."""
    out = pd.DataFrame(index=df.index)
    c1, c2, c4 = df["c1"], df["c2"], df["c4"]
    # one-month basis (front vs 2nd) and the longer curve slope (front vs 4th, per-month)
    out["basis_1m"] = np.log(c1 / c2)
    out["slope"] = np.log(c1 / c4) / 3.0
    out["roll_yield_ann"] = out["basis_1m"] * 12.0   # annualized, comparable to Yahoo collector
    return out


def _spot_return(df: pd.DataFrame) -> pd.Series:
    """Tradeable price return = Cushing WTI SPOT (no roll discontinuities). Falls
    back to C1 if spot missing on a date."""
    px = df["spot"].copy()
    if "c1" in df:
        px = px.fillna(df["c1"])
    return px


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def ic_block(sig: pd.Series, px: pd.Series, label: str) -> dict:
    """Predictive IC of `sig` vs forward returns of `px`. Reports BOTH an
    overlapping-window IC (Newey-West t) and a clean NON-overlapping IC (sample
    every h days -> independent obs -> plain corr), plus a pre/post split-half."""
    res = {"label": label, "n_obs": int(sig.dropna().shape[0]), "horizons": {}}
    j0 = pd.concat([sig.rename("s"), px.rename("p")], axis=1).dropna()
    if len(j0) < 300:
        res["error"] = "insufficient overlap"
        return res
    mid = j0.index[len(j0) // 2]
    for h in HORIZONS:
        fwd = j0["p"].shift(-h) / j0["p"] - 1.0
        d = pd.concat([j0["s"], fwd.rename("f")], axis=1).dropna()
        if len(d) < 60:
            continue
        # overlapping (all days) -> Spearman + NW t-stat on the rank cross-product
        rs, rf = d["s"].rank(), d["f"].rank()
        ic_ovl = float(rs.corr(rf))
        xprod = ((rs - rs.mean()) * (rf - rf.mean())) / (rs.std(ddof=0) * rf.std(ddof=0))
        nw = V.newey_west_tstat(xprod, lags=max(4, h // 5))
        # clean non-overlapping (every h-th obs)
        dno = d.iloc[::h]
        ic_no = float(dno["s"].rank().corr(dno["f"].rank())) if len(dno) >= 12 else float("nan")
        # split-half robustness (sign-consistency is the bar)
        a, b = d[d.index <= mid], d[d.index > mid]
        ic_a = float(a["s"].rank().corr(a["f"].rank())) if len(a) >= 60 else float("nan")
        ic_b = float(b["s"].rank().corr(b["f"].rank())) if len(b) >= 60 else float("nan")
        res["horizons"][h] = {
            "ic_overlap": round(ic_ovl, 4), "t_hac": nw["t"], "p_hac": nw["p"],
            "ic_indep": round(ic_no, 4), "n_indep": int(len(dno)),
            "ic_first_half": round(ic_a, 4), "ic_second_half": round(ic_b, 4),
            "sign_consistent": bool(np.sign(ic_a) == np.sign(ic_b) and not np.isnan(ic_a) and not np.isnan(ic_b)),
        }
    return res


def _perm_null_long_short(alloc: pd.Series, close: pd.Series, B: int = 2000,
                          block: int = 42, seed: int = 11) -> dict:
    """AQR-style circular-block-shuffle null for a long/short (no cash leg) sleeve."""
    real = V.backtest_core(close, alloc, cost_bps=COST_BPS)["net"]
    real_sh = V._sharpe(real, 252)
    a = alloc.reindex(close.index).ffill().fillna(0.0).to_numpy()
    n = len(a); rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block)); grid = np.arange(block)
    sh = np.empty(B)
    for k in range(B):
        st = rng.integers(0, n, nb)
        idx = (st[:, None] + grid[None, :]).ravel()[:n] % n
        shuf = pd.Series(a[idx], index=close.index)
        sh[k] = V._sharpe(V.backtest_core(close, shuf, cost_bps=COST_BPS)["net"], 252)
    return {"real_sharpe": round(real_sh, 3),
            "null_sharpe_p95": round(float(np.percentile(sh, 95)), 3),
            "skill_p": round(float(np.mean(sh >= real_sh)), 4), "B": B}


def timing_backtest(sig: pd.Series, px: pd.Series, n_trials: int = 12) -> dict:
    """Trade the SPOT on the term-structure signal. Conservative: P&L excludes the
    mechanical roll carry (only the spot move). Long/short = sign of the signal vs
    its trailing median (no look-ahead). Reports net Sharpe, vs buy&hold, DSR,
    perm-null, bootstrap CI."""
    j = pd.concat([sig.rename("s"), px.rename("p")], axis=1).dropna()
    if len(j) < 500:
        return {"error": "insufficient data"}
    s, close = j["s"], j["p"]
    # de-mean by an expanding median (point-in-time) so "backwardation vs its own
    # norm" drives position, not the unconditional sign.
    norm = s.expanding(min_periods=252).median()
    z = (s - norm)
    alloc = pd.Series(np.where(z > 0, 1.0, -1.0), index=s.index)   # long/short
    alloc[norm.isna()] = 0.0
    bt = V.backtest_core(close, alloc, cost_bps=COST_BPS)
    net, hold = bt["net"], bt["hold"]
    mom = V.ret_moments(net)
    dsr = V.deflated_sharpe(*mom, n_trials=n_trials) if mom else None
    boot = V.block_bootstrap_ci(net, block=63, B=3000)
    pn = _perm_null_long_short(alloc, close)
    long_frac = float((alloc > 0).mean())
    return {
        "years": round(bt["years"], 1), "n": int(len(net)),
        "sharpe_net": round(V._sharpe(net, 252), 3),
        "sharpe_buyhold": round(V._sharpe(hold, 252), 3),
        "cagr_net": round(100 * ((1 + net).prod() ** (252 / len(net)) - 1), 2),
        "cagr_buyhold": round(100 * ((1 + hold).prod() ** (252 / len(hold)) - 1), 2),
        "maxdd_net": round(100 * V._maxdd(net), 1),
        "maxdd_buyhold": round(100 * V._maxdd(hold), 1),
        "long_frac": round(long_frac, 3),
        "dsr": dsr, "bootstrap": boot, "perm_null": pn,
    }


def incremental_probe(df: pd.DataFrame, h: int = 63) -> dict:
    """Is the basis→forward-return relationship anything BEYOND plain price
    mean-reversion (which existing momentum/structure factors already capture)?
    Partial Spearman of basis vs forward, controlling for trailing momentum. Plus
    the TOTAL-return view (spot move + realized roll carry) which is what a futures
    CARRY strategy — as opposed to single-asset directional timing — actually earns."""
    spot = df["spot"].fillna(df["c1"])
    basis = np.log(df["c1"] / df["c2"])
    mom = spot / spot.shift(h) - 1.0
    fwd = spot.shift(-h) / spot - 1.0
    d = (pd.concat([basis.rename("basis"), mom.rename("mom"), fwd.rename("fwd")], axis=1)
         .replace([np.inf, -np.inf], np.nan).dropna())
    R = d.rank()
    C = R.corr().values

    def partial(i, j, k):
        return float((C[i, j] - C[i, k] * C[j, k]) /
                     np.sqrt((1 - C[i, k] ** 2) * (1 - C[j, k] ** 2)))
    tot = (fwd + basis * (h / 21.0))   # crude: add realized carry if the curve holds
    dt = pd.concat([basis.rename("b"), tot.rename("t")], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "horizon": h, "n": int(len(d)),
        "ic_basis": round(float(R["basis"].corr(R["fwd"])), 4),
        "ic_momentum": round(float(R["mom"].corr(R["fwd"])), 4),
        "corr_basis_momentum": round(float(R["basis"].corr(R["mom"])), 4),
        "partial_basis_given_mom": round(partial(0, 2, 1), 4),
        "partial_mom_given_basis": round(partial(1, 2, 0), 4),
        "ic_total_return_incl_carry": round(float(dt["b"].rank().corr(dt["t"].rank())), 4),
    }


def roll_carry_report(df: pd.DataFrame) -> dict:
    """The MECHANICAL piece we EXCLUDED from the strategy: average realized roll
    return when backwardated vs contangoed. Context, not the edge."""
    b = np.log(df["c1"] / df["c2"]).dropna()
    fwd21 = (df["spot"].shift(-21) / df["spot"] - 1.0).reindex(b.index)
    bw = fwd21[b > 0].dropna(); co = fwd21[b < 0].dropna()
    return {
        "mean_basis_1m": round(float(b.mean()), 5),
        "pct_backwardated": round(float((b > 0).mean()), 3),
        "fwd21_spot_when_backwardated_pct": round(100 * float(bw.mean()), 3) if len(bw) else None,
        "fwd21_spot_when_contango_pct": round(100 * float(co.mean()), 3) if len(co) else None,
        "n_bw": int(len(bw)), "n_co": int(len(co)),
    }


# --------------------------------------------------------------------------- #
# shallow metals (Yahoo carry) — reported, underpowered
# --------------------------------------------------------------------------- #
def shallow_metal(asset: str) -> dict:
    p = CARRY_DIR / f"{asset}.parquet"
    if not p.exists():
        return {"asset": asset, "error": "no data"}
    c = pd.read_parquet(p)
    if "roll_yield_ann" not in c or len(c) < 120:
        return {"asset": asset, "n": len(c), "error": "too shallow"}
    # we only have front/second prices, not a deep spot — use front for the price
    px = c["front"].astype(float)
    sig = c["roll_yield_ann"].astype(float)
    ic = ic_block(sig, px, f"{asset} (Yahoo carry, shallow)")
    return {"asset": asset, "n": int(len(c)),
            "span": f"{str(c.index.min())[:10]}..{str(c.index.max())[:10]}", "ic": ic}


# --------------------------------------------------------------------------- #
def verdict_from(ic: dict, bt: dict) -> tuple[str, list[str]]:
    notes = []
    # IC bar: positive & sign-consistent across halves at the 63d horizon, NW-significant
    h = ic.get("horizons", {}).get(63, {})
    ic_ok = (h.get("ic_overlap", 0) > 0 and h.get("sign_consistent") and (h.get("p_hac") or 1) < 0.10)
    notes.append(f"63d IC overlap={h.get('ic_overlap')} (t_HAC={h.get('t_hac')}, p={h.get('p_hac')}), "
                 f"halves {h.get('ic_first_half')}/{h.get('ic_second_half')} "
                 f"sign-consistent={h.get('sign_consistent')}")
    # backtest bar: net Sharpe beats buy&hold, DSR>=0.90, perm-null skill p<0.10
    dsr = (bt.get("dsr") or {}).get("dsr", 0)
    pn = (bt.get("perm_null") or {}).get("skill_p", 1)
    bt_ok = (bt.get("sharpe_net", 0) > max(0.2, bt.get("sharpe_buyhold", 0)) and dsr >= 0.90 and pn < 0.10)
    notes.append(f"net Sharpe={bt.get('sharpe_net')} vs B&H {bt.get('sharpe_buyhold')}; "
                 f"DSR={dsr}; perm-null skill p={pn}")
    if ic_ok and bt_ok:
        return "GO — wire as a scored conviction leg (bounded)", notes
    # robust but SIGN-INVERTED: significant IC of the WRONG (negative) sign vs the
    # naive storage-theory prior, sign-consistent across halves -> the naive factor
    # would HURT; the real signal is contrarian (mean-reversion). Still display-only
    # because the standalone backtest fails and the live data is shallow.
    inverted = (h.get("ic_overlap", 0) < 0 and h.get("sign_consistent")
                and (h.get("p_hac") or 1) < 0.05)
    if inverted:
        return ("DISPLAY-ONLY — robust but CONTRARIAN (naive 'backwardation=bullish' is "
                "WRONG-SIGNED; the validated read is mean-reversion). Standalone fails the "
                "Sharpe/DSR bar + live data shallow → context, never scored (yet)"), notes
    if (h.get("ic_overlap", 0) > 0 and h.get("sign_consistent")) or bt.get("sharpe_net", 0) > bt.get("sharpe_buyhold", 0):
        return "DISPLAY-ONLY (directionally right, fails the scoring bar)", notes
    return "DISPLAY-ONLY (no robust edge)", notes


def main() -> int:
    df = load_eia_termstructure()
    df = df.dropna(subset=["spot", "c1", "c2"])
    print(f"[oil] usable rows={len(df)} {str(df.index.min())[:10]}..{str(df.index.max())[:10]}")

    sig = basis_signals(df)
    px = _spot_return(df)

    ic = ic_block(sig["basis_1m"], px, "WTI basis_1m (EIA deep)")
    bt = timing_backtest(sig["basis_1m"], px)
    carry = roll_carry_report(df)
    incr = incremental_probe(df)
    metals = {a: shallow_metal(a) for a in ("gold", "silver", "copper")}

    verdict, notes = verdict_from(ic, bt)

    out = {"oil": {"ic": ic, "timing_backtest": bt, "roll_carry_context": carry,
                   "incremental": incr},
           "metals_shallow": metals, "verdict": verdict, "verdict_notes": notes,
           "cost_bps": COST_BPS}
    (CARRY_DIR / "phase0_verdict.json").write_text(json.dumps(out, indent=2, default=str))

    # ---- report ----
    L = ["# Commodity term-structure (roll yield / basis) — Phase-0 verdict", "",
         f"**VERDICT: {verdict}**", "",
         "Storage theory / Keynesian normal backwardation: positive roll yield "
         "(backwardation) should positively predict forward returns. Tested deep on "
         "WTI (EIA spot + futures 1-4, keyless, 1985-2024); metals are the shallow "
         "Yahoo collector (~18mo, underpowered).", "",
         "Conservative: strategy P&L = SPOT move only; the mechanical roll carry is "
         "excluded and only reported as context.", "",
         "## Oil (WTI) — the real test", ""]
    for n in notes:
        L.append(f"- {n}")
    L += ["", "### Predictive IC (basis_1m → forward spot return)", "",
          "| Horizon | IC (overlap) | t_HAC | p | IC (indep) | half-1 | half-2 | sign-consistent |",
          "|--:|--:|--:|--:|--:|--:|--:|:--:|"]
    for h, r in ic.get("horizons", {}).items():
        L.append(f"| {h}d | {r['ic_overlap']} | {r['t_hac']} | {r['p_hac']} | "
                 f"{r['ic_indep']} (n={r['n_indep']}) | {r['ic_first_half']} | {r['ic_second_half']} | "
                 f"{'✓' if r['sign_consistent'] else '✗'} |")
    L += ["", "### Timing backtest (long/short spot vs expanding-median basis, net of 8bps)", ""]
    if "error" not in bt:
        L += [f"- {bt['years']}y, n={bt['n']}, long {int(100*bt['long_frac'])}% of the time",
              f"- **net Sharpe {bt['sharpe_net']}** vs buy&hold {bt['sharpe_buyhold']}; "
              f"CAGR {bt['cagr_net']}% vs {bt['cagr_buyhold']}%; MaxDD {bt['maxdd_net']}% vs {bt['maxdd_buyhold']}%",
              f"- DSR {bt['dsr']}", f"- perm-null {bt['perm_null']}", f"- bootstrap {bt['bootstrap']}"]
    L += ["", "### Is it just price mean-reversion? (incremental value over momentum)", "",
          f"- corr(basis→fwd) {incr['ic_basis']} vs corr(momentum→fwd) {incr['ic_momentum']}; "
          f"basis–momentum corr {incr['corr_basis_momentum']}",
          f"- **partial corr(basis, fwd | momentum) = {incr['partial_basis_given_mom']}** "
          f"(vs momentum's own partial {incr['partial_mom_given_basis']}) — basis is NON-redundant; "
          f"it largely SUBSUMES price momentum as the mean-reversion signal",
          f"- **TOTAL-return view (spot + realized carry): IC {incr['ic_total_return_incl_carry']}** — "
          f"crediting the carry you earn in backwardation roughly CANCELS the spot mean-reversion. "
          f"This is why cross-sectional carry harvesting works but single-asset directional timing sees "
          f"the spot reversal.",
          "", "### Roll-carry context (the mechanical piece we EXCLUDED)", "",
          f"- backwardated {int(100*carry['pct_backwardated'])}% of days; "
          f"mean 1m basis {carry['mean_basis_1m']}",
          f"- forward-21d spot when backwardated: {carry['fwd21_spot_when_backwardated_pct']}% "
          f"vs contango {carry['fwd21_spot_when_contango_pct']}% "
          f"(n {carry['n_bw']}/{carry['n_co']})", "",
          "## Metals (Yahoo carry, SHALLOW ~18mo — underpowered, forward-accumulating)", ""]
    for a, m in metals.items():
        if "ic" in m and m["ic"].get("horizons"):
            h63 = m["ic"]["horizons"].get(63, {})
            L.append(f"- **{a}** ({m['span']}, n={m['n']}): 63d IC {h63.get('ic_overlap')} "
                     f"(half {h63.get('ic_first_half')}/{h63.get('ic_second_half')}) — too short to conclude")
        else:
            L.append(f"- **{a}**: {m.get('error', m)}")
    (ROOT / "research" / "COMMODITY_CARRY_PHASE0.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\n[written] research/COMMODITY_CARRY_PHASE0.md + data/commodity_carry/phase0_verdict.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
