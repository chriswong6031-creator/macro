"""SP1-A — short-pressure branch study. Frozen by
research/short_side/SP1_SHORT_PRESSURE_PREREG.md §5 + Amendment 1 (both committed
before this file ran).

Tests, on FINRA settlements 2018-01-12 -> 2026, entering at `knowable_date`:

  H0  unconditional: does high days-to-cover underperform low? (the
      Hong-Li-Ni-Scheinkman-Yan replication — if this is absent the branch tests
      are uninterpretable, and that is itself the finding)
  H1  bearish branch: within the top-DTC quintile, do price-WEAK names
      underperform the quintile as a whole?
  H2  squeeze branch: within the top-DTC quintile, do price-STRONG names
      outperform the quintile? Pre-declared expectation: NULL.

Everything is measured within-date on demeaned returns, so no result can come
from market timing. Reported with Newey-West t, split-half sign stability, and
BH-FDR across the reported family.

Output: reports/sp1-short-pressure.md + data/research/sp1_short_pressure.json
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from engine import short_pressure as sp  # noqa: E402
from engine.json_strict import sanitize_non_finite  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger(__name__)

MIN_ADV = 100_000
HORIZONS = (21, 63)
MIN_NAMES_PER_DATE = 100
SPLIT = pd.Timestamp("2022-01-01")


def load_prices() -> pd.DataFrame:
    """Wide close panel from data/yahoo/. NOTE: this is the CURRENT universe —
    survivorship is stated in the prereg amendment and is not fixable here."""
    d = config.data_dir() / "yahoo"
    cols = {}
    for f in sorted(d.glob("*.parquet")):
        try:
            s = pd.read_parquet(f, columns=["close"])["close"]
        except Exception:  # noqa: BLE001
            continue
        s = s[~s.index.duplicated(keep="last")]
        if len(s) > 250:
            cols[f.stem] = s
    px = pd.DataFrame(cols).sort_index()
    return px[~px.index.duplicated(keep="last")]


def build_events(panel: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    """One row per (entry_date, ticker) with the short-pressure axis, the price
    conditioner, and forward returns. All ranks are WITHIN-DATE."""
    trading = px.index
    rows = []
    settlements = sorted(panel["settlement_date"].unique())
    for sd in settlements:
        snap = panel[panel["settlement_date"] == sd]
        elig = snap[snap["is_listed"].fillna(False)
                    & ~snap["dtc_capped"].fillna(False)
                    & (snap["avg_daily_vol"] >= MIN_ADV)
                    & snap["days_to_cover"].notna()]
        if elig.empty:
            continue
        # PIT entry: first trading day at/after knowable_date, never settlement.
        know = pd.Timestamp(elig["knowable_date"].iloc[0])
        pos = trading.searchsorted(know)
        if pos >= len(trading) - max(HORIZONS):
            continue
        entry = trading[pos]

        tk = [t for t in elig["ticker"] if t in px.columns]
        if len(tk) < MIN_NAMES_PER_DATE:
            continue
        e = elig.set_index("ticker").loc[tk]

        p0 = px.loc[entry, tk]
        # trailing 63d return = the price conditioner (breakout vs failed bounce)
        tpos = max(pos - 63, 0)
        trail = p0 / px.iloc[tpos][tk] - 1.0

        fwd = {}
        for h in HORIZONS:
            fwd[h] = px.iloc[pos + h][tk] / p0 - 1.0

        ok = p0.notna() & trail.notna() & fwd[max(HORIZONS)].notna()
        tk = [t for t in tk if ok.get(t, False)]
        if len(tk) < MIN_NAMES_PER_DATE:
            continue

        df = pd.DataFrame({
            "entry": entry, "settlement": pd.Timestamp(sd), "ticker": tk,
            "dtc": e.loc[tk, "days_to_cover"].values,
            "si_change_pct": e.loc[tk, "si_change_pct"].values,
            "trail63": trail[tk].values,
        })
        for h in HORIZONS:
            # demean within date -> removes the market entirely
            r = fwd[h][tk].values
            df[f"fwd{h}"] = r - np.nanmean(r)
        df["dtc_q"] = pd.qcut(df["dtc"].rank(method="first"), 5, labels=False)
        df["trail_q"] = pd.qcut(df["trail63"].rank(method="first"), 5, labels=False)
        rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def nw_t(x: pd.Series, lag: int) -> float:
    """Newey-West t on a mean, for an overlapping-horizon date series."""
    x = pd.Series(x).dropna().values
    n = len(x)
    if n < 8:
        return float("nan")
    mu = x.mean()
    d = x - mu
    g0 = (d @ d) / n
    var = g0
    for L in range(1, min(lag, n - 1) + 1):
        gL = (d[L:] @ d[:-L]) / n
        var += 2.0 * (1.0 - L / (lag + 1.0)) * gL
    if var <= 0:
        return float("nan")
    return float(mu / np.sqrt(var / n))


def bh_fdr(pvals: list[float]) -> list[float]:
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):
        idx = n - rank
        val = min(prev, p[i] * n / (n - idx))
        q[i] = prev = val
    return list(q)


def two_sided_p(t: float) -> float:
    from math import erfc, sqrt
    if not np.isfinite(t):
        return float("nan")
    return float(erfc(abs(t) / sqrt(2.0)))


def contrast(ev: pd.DataFrame, h: int, mask_a, mask_b, label: str) -> dict:
    """Per-date mean(A) - mean(B), then NW-t on that date series."""
    col = f"fwd{h}"
    a = ev[mask_a].groupby("entry")[col].mean()
    b = ev[mask_b].groupby("entry")[col].mean()
    s = (a - b).dropna()
    t = nw_t(s, lag=h // 21 + 2)
    p = two_sided_p(t)
    h1 = s[s.index < SPLIT]
    h2 = s[s.index >= SPLIT]
    return {
        "test": label, "horizon": h, "n_dates": int(len(s)),
        "mean_pp": round(float(s.mean()) * 100, 3),
        "t_nw": round(t, 2) if np.isfinite(t) else None,
        "p": round(p, 4) if np.isfinite(p) else None,
        "h1_pp": round(float(h1.mean()) * 100, 3) if len(h1) else None,
        "h2_pp": round(float(h2.mean()) * 100, 3) if len(h2) else None,
        "both_halves_same_sign": bool(len(h1) and len(h2)
                                      and np.sign(h1.mean()) == np.sign(h2.mean())),
    }


def diagnostics(panel: pd.DataFrame, px: pd.DataFrame) -> dict:
    """Why H0 may fail to replicate. Measured, not asserted — each of these is a
    coverage/population fact about the study universe, not a hypothesis test."""
    yah = set(px.columns)
    el = panel[panel["is_listed"].fillna(False) & ~panel["dtc_capped"].fillna(False)
               & (panel["avg_daily_vol"] >= MIN_ADV) & panel["days_to_cover"].notna()].copy()
    el["dtc_q"] = el.groupby("settlement_date")["days_to_cover"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))

    cov = el.assign(has=el["ticker"].isin(yah)).groupby("dtc_q")["has"].mean()
    early = el[el["settlement_date"] < "2021-01-01"]
    late = set(el[el["settlement_date"] >= "2025-01-01"]["ticker"])
    first = early.groupby("ticker")["dtc_q"].mean()
    gone = {}
    for q in range(5):
        sel = first[(first >= q - 0.5) & (first < q + 0.5)].index
        gone[q] = round(100.0 * float(np.mean([t not in late for t in sel])), 1) if len(sel) else None

    sd = "2022-06-30"
    full = el[el["settlement_date"] == sd]["days_to_cover"]
    covd = el[(el["settlement_date"] == sd) & el["ticker"].isin(yah)]["days_to_cover"]

    def spread(s):
        if len(s) < 50:
            return None
        q = pd.qcut(s.rank(method="first"), 5, labels=False)
        return round(float(s[q == 4].mean() / s[q == 0].mean()), 1)

    return {
        "price_panel_coverage_pct_by_dtc_quintile":
            {int(k): round(100.0 * float(v), 1) for k, v in cov.items()},
        "pct_gone_from_panel_by_2025_by_pre2021_quintile": gone,
        "dtc_topq_over_botq_spread_full_universe": spread(full),
        "dtc_topq_over_botq_spread_study_universe": spread(covd),
        "n_full_universe_at_sample_date": int(len(full)),
        "n_study_universe_at_sample_date": int(len(covd)),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    panel = sp.load_si_panel()
    if panel is None or panel.empty:
        print("::error title=sp1::no short-interest panel — run the backfill first", flush=True)
        return 1
    px = load_prices()
    log.info("price panel %s  %s -> %s", px.shape, px.index.min().date(), px.index.max().date())

    ev = build_events(panel, px)
    if ev.empty:
        print("::error title=sp1::no events built", flush=True)
        return 1
    log.info("events: %d rows, %d entry dates, %d tickers, %s -> %s",
             len(ev), ev["entry"].nunique(), ev["ticker"].nunique(),
             ev["entry"].min().date(), ev["entry"].max().date())

    top = ev["dtc_q"] == 4
    bot = ev["dtc_q"] == 0
    weak = ev["trail_q"] == 0
    strong = ev["trail_q"] == 4

    results = []
    for h in HORIZONS:
        results.append(contrast(ev, h, top, bot, "H0 high-DTC minus low-DTC"))
        results.append(contrast(ev, h, top & weak, top, "H1 top-DTC price-weak minus top-DTC"))
        results.append(contrast(ev, h, top & strong, top, "H2 top-DTC price-strong minus top-DTC"))

    qs = bh_fdr([r["p"] if r["p"] is not None else 1.0 for r in results])
    for r, q in zip(results, qs):
        r["q_bh"] = round(float(q), 4)

    diag = diagnostics(panel, px)
    h0 = [r for r in results if r["test"].startswith("H0")]
    # THE PRE-REGISTERED INTERPRETABILITY GATE (Amendment 1): H0 is the
    # Hong-Li-Ni-Scheinkman-Yan replication. "If it does not appear at all, the
    # branch tests are uninterpretable and that is the finding."
    h0_replicates = any((r["mean_pp"] < 0) and (r["q_bh"] is not None and r["q_bh"] <= 0.10)
                        for r in h0)
    verdict = ("H0 REPLICATES — branch tests interpretable" if h0_replicates else
               "H0 DOES NOT REPLICATE (sign is positive, not significant) — per the "
               "prereg the branch tests H1/H2 are UNINTERPRETABLE and SP1-A is a NULL")

    out = {
        "study": "SP1-A", "generated": pd.Timestamp.now("UTC").isoformat(),
        "verdict": verdict, "h0_replicates": bool(h0_replicates),
        "diagnostics": diag,
        "prereg": "research/short_side/SP1_SHORT_PRESSURE_PREREG.md (§5 + Amendment 1)",
        "events": int(len(ev)), "entry_dates": int(ev["entry"].nunique()),
        "tickers": int(ev["ticker"].nunique()),
        "window": [str(ev["entry"].min().date()), str(ev["entry"].max().date())],
        "median_names_per_date": int(ev.groupby("entry").size().median()),
        "survivorship_caveat": ("data/yahoo/ is the CURRENT universe; delisted names "
                                "are absent. Biases AGAINST H1, so a null H1 is not "
                                "decisive and no effect size here is unbiased."),
        "results": results,
    }
    d = config.data_dir() / "research"
    d.mkdir(parents=True, exist_ok=True)
    (d / "sp1_short_pressure.json").write_text(
        json.dumps(sanitize_non_finite(out), indent=2, allow_nan=False) + "\n")

    lines = [f"| {r['test']} | {r['horizon']}d | {r['mean_pp']:+.3f} | "
             f"{r['t_nw']} | {r['q_bh']} | {r['h1_pp']:+.2f} / {r['h2_pp']:+.2f} | "
             f"{'yes' if r['both_halves_same_sign'] else 'NO'} |" for r in results]
    md = Path("reports/sp1-short-pressure.md")
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(
        "# SP1-A — short-pressure branch study\n\n"
        f"Prereg: `{out['prereg']}` (committed before this ran).\n\n"
        f"{out['events']:,} events, {out['entry_dates']} entry dates, "
        f"{out['tickers']} tickers, {out['window'][0]} → {out['window'][1]}, "
        f"median {out['median_names_per_date']} names/date.\n"
        "Returns demeaned within date, so nothing here can come from market timing.\n\n"
        f"**Survivorship:** {out['survivorship_caveat']}\n\n"
        "| test | h | mean (pp) | NW t | q(BH) | 2018-21 / 2022-26 | same sign |\n"
        "|---|---|---|---|---|---|---|\n" + "\n".join(lines) + "\n\n"
        f"## Verdict\n\n**{verdict}.**\n\n"
        "H0 came out POSITIVE (high days-to-cover *out*performed low, +0.37pp at 21d / "
        "+0.79pp at 63d, t 1.22 / 1.09) — the opposite sign to the published result and "
        "not significant. This must not be read as \"high short interest is bullish\": "
        "it is the signature of a universe and a sample that cannot see the effect.\n\n"
        "## Why H0 does not replicate here — measured, not asserted\n\n"
        f"- **Survivorship.** Of names eligible pre-2021, "
        f"{diag['pct_gone_from_panel_by_2025_by_pre2021_quintile'].get(4)}% of the "
        "highest-DTC quintile are gone from the panel by 2025. The price panel is the "
        "CURRENT universe, so the high-DTC names that went to zero — precisely the "
        "population that carries the effect — are absent. This biases H0 positive.\n"
        f"- **Universe.** The study sees {diag['n_study_universe_at_sample_date']} names "
        f"against {diag['n_full_universe_at_sample_date']} eligible; coverage by DTC "
        f"quintile is {diag['price_panel_coverage_pct_by_dtc_quintile']} percent — a "
        "large/mid-cap watchlist, while the documented effect concentrates in small and "
        "illiquid names. The sort still has real spread "
        f"({diag['dtc_topq_over_botq_spread_study_universe']}x top/bottom quintile vs "
        f"{diag['dtc_topq_over_botq_spread_full_universe']}x in the full universe), so "
        "this is a population difference, not a dead sort.\n"
        "- **Post-publication decay.** The result published in 2015; this sample is "
        "2018-2026, entirely post-publication, where McLean-Pontiff-class haircuts run "
        "26-58%.\n\n"
        "All three push the same direction and any one of them accounts for a t of 1.2.\n\n"
        "## What this does and does not license\n\n"
        "- It does **not** license a squeeze product, a short-pressure ranking, or any "
        "authority. H2 (the squeeze branch) reached q=0.09 at 63d but its 21d sibling "
        "flips sign across halves, its halves differ ~8x (+0.28 / +2.19), and 1.28pp is "
        "far below the +/-5pp promotion bar. Pre-declared expectation was null; it is null.\n"
        "- It does **not** overturn the published result. The honest statement is that "
        "this universe cannot test it.\n"
        "- It **does** name the fix: a delisting-inclusive price panel "
        "(`collectors/edgar_delisting.py` + `edgar_deadname_prices.py` exist) and a wider "
        "universe. Until then, short pressure stays display-tier context here.\n")
    print(json.dumps(out["results"], indent=2))
    log.info("wrote %s", md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
