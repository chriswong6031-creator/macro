"""Bitcoin Vector calibration — the house rule applied to crypto signals.

Every signal band earns a MEASURED forward-return record before the dashboard
is allowed to make any claim about it. We learned this the hard way on the
macro heat board (D31: the confluence score was INVERTED vs forward returns);
the same discipline applies here, with even thinner history (~3.5 BTC cycles).

Outputs (written to reports/ + data/vector/):
  1. Forward-return records per band for Risk Index, Momentum, Structure, BFI,
     Risk Oscillator — count / hit-rate / mean / median at 7/30/90d.
  2. Split-half robustness: same tables on pre/post `split_date`; a relationship
     is "robust" only if its sign holds in BOTH halves.
  3. Allocation backtest vs HODL for all 4 variants: CAGR, Sharpe, Sortino,
     MaxDD, time-in-market (the Vector scorecard metrics).
  4. Whipsaw stats per state signal.
  5. A verdict block: which signals are CONFIRMED (monotone + robust), which are
     CONTEXT-ONLY (weak/unstable), which are INVERTED (flag loudly).

Run: .venv/bin/python -m scripts.calibrate_vector
No look-ahead: signals are close-based, so the backtest acts on shift(1).
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine import btc_signals  # noqa: E402
from lib import config, store  # noqa: E402

TRADING_YEAR = 365  # BTC trades every day


# --------------------------------------------------------------------------- #
# forward-return record per band
# --------------------------------------------------------------------------- #
def forward_returns(close: pd.Series, horizons: list[int]) -> pd.DataFrame:
    return pd.DataFrame({h: close.shift(-h) / close - 1 for h in horizons})


def forward_drawdown(close: pd.Series, horizons: list[int]) -> pd.DataFrame:
    """Worst close-to-close drawdown over the next h days — the CORRECT test
    for a risk gauge (a high reading should precede deeper drawdowns even if
    price eventually recovers; forward *return* misses that because extreme
    risk also marks capitulation bottoms — the U-shape we found)."""
    out = {}
    for h in horizons:
        fwd_min = close[::-1].rolling(h, min_periods=1).min()[::-1].shift(-1)
        out[h] = fwd_min / close - 1
    return pd.DataFrame(out)


def drawdown_table(signal: pd.Series, fdd: pd.DataFrame, bands: list,
                   labels: list[str], horizons: list[int]) -> pd.DataFrame:
    cats = pd.cut(signal, bins=bands, labels=labels, include_lowest=True)
    rows = []
    for lab in labels:
        mask = cats == lab
        rec = {"band": lab, "n": int(mask.sum())}
        for h in horizons:
            d = fdd.loc[mask, h].dropna()
            rec[f"avgDD_{h}d"] = round(100 * d.mean(), 2) if len(d) else np.nan
            rec[f"p05DD_{h}d"] = round(100 * d.quantile(0.05), 2) if len(d) else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def band_table(signal: pd.Series, fwd: pd.DataFrame, bands: list, labels: list[str],
               horizons: list[int]) -> pd.DataFrame:
    """Bucket `signal` into bands (numeric edges) or categories (list of values)."""
    rows = []
    if isinstance(bands[0], (list, tuple)):  # categorical: each band is a set of values
        grouping = [(lab, signal.isin(vals if isinstance(vals, (list, tuple)) else [vals]))
                    for lab, vals in zip(labels, bands)]
    else:  # numeric edges
        cats = pd.cut(signal, bins=bands, labels=labels, include_lowest=True)
        grouping = [(lab, cats == lab) for lab in labels]
    for lab, mask in grouping:
        n = int(mask.sum())
        rec = {"band": lab, "n": n}
        for h in horizons:
            r = fwd.loc[mask, h].dropna()
            if len(r):
                rec[f"hit_{h}d"] = round(100 * (r > 0).mean(), 1)
                rec[f"mean_{h}d"] = round(100 * r.mean(), 2)
            else:
                rec[f"hit_{h}d"], rec[f"mean_{h}d"] = np.nan, np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def monotone(table: pd.DataFrame, col: str) -> int:
    """+1 if `col` increases down the bands, -1 if decreases, 0 if neither."""
    v = table[col].dropna().values
    if len(v) < 2:
        return 0
    d = np.diff(v)
    if (d >= 0).all() and (d > 0).any():
        return 1
    if (d <= 0).all() and (d < 0).any():
        return -1
    return 0


def rank_trend(table: pd.DataFrame, col: str, n_floor: int = 150) -> int:
    """Robust direction: Spearman sign between band order and `col`, ignoring
    bands thinner than n_floor (small-sample tails shouldn't veto a real trend).
    Returns +1 / -1 / 0."""
    t = table[table["n"] >= n_floor] if "n" in table.columns else table
    v = t[col].dropna().values
    if len(v) < 3:
        return 0
    order = np.arange(len(v))
    rho = np.corrcoef(order, v)[0, 1]
    return 1 if rho > 0.6 else (-1 if rho < -0.6 else 0)


# --------------------------------------------------------------------------- #
# allocation backtest
# --------------------------------------------------------------------------- #
def backtest(close: pd.Series, alloc: pd.Series) -> dict:
    ret = close.pct_change().fillna(0)
    pos = alloc.shift(1).reindex(ret.index).ffill().fillna(0)  # act next day
    strat = pos * ret
    eq = (1 + strat).cumprod()
    hodl = (1 + ret).cumprod()
    years = (close.index[-1] - close.index[0]).days / 365.25

    def cagr(e):
        return (e.iloc[-1]) ** (1 / years) - 1 if years > 0 and e.iloc[-1] > 0 else np.nan

    def sharpe(r):
        sd = r.std()
        return (r.mean() / sd * np.sqrt(TRADING_YEAR)) if sd else np.nan

    def sortino(r):
        dn = r[r < 0].std()
        return (r.mean() / dn * np.sqrt(TRADING_YEAR)) if dn else np.nan

    def maxdd(e):
        return float((e / e.cummax() - 1).min())

    return {
        "cagr": round(100 * cagr(eq), 1), "hodl_cagr": round(100 * cagr(hodl), 1),
        "sharpe": round(sharpe(strat), 2), "hodl_sharpe": round(sharpe(ret), 2),
        "sortino": round(sortino(strat), 2), "hodl_sortino": round(sortino(ret), 2),
        "maxdd": round(100 * maxdd(eq), 1), "hodl_maxdd": round(100 * maxdd(hodl), 1),
        "time_in_market": round(100 * (pos > 0).mean(), 1),
        "total_return": round(100 * (eq.iloc[-1] - 1), 0),
        "hodl_total_return": round(100 * (hodl.iloc[-1] - 1), 0),
        "final_vs_hodl": round(eq.iloc[-1] / hodl.iloc[-1], 2),
    }


def whipsaw(state: pd.Series, max_days: int) -> dict:
    s = state.dropna()
    seg = (s != s.shift()).cumsum()
    sizes = s.groupby(seg).size()
    changes = len(sizes) - 1
    whips = int((sizes.iloc[1:] < max_days).sum()) if changes > 0 else 0
    return {"changes": changes, "whipsaws": whips,
            "pct": round(100 * whips / changes, 1) if changes else 0.0}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    cfg = config.load()["vector"]["calibration"]
    horizons = cfg["forward_days"]
    df = btc_signals.compute_all()
    df = df.loc[cfg["start_date"]:].copy()
    close = df["close"]
    fwd = forward_returns(close, horizons)
    fdd = forward_drawdown(close, horizons)

    halves = {
        "full": df.index,
        "pre": df.index[df.index < cfg["split_date"]],
        "post": df.index[df.index >= cfg["split_date"]],
    }

    SIGNALS = {
        "risk_index": {
            "bands": [-0.1, 25, 50, 75, 100],
            "labels": ["0-25", "25-50", "50-75", "75-100"],
            "want": -1,  # higher risk SHOULD mean lower forward return
        },
        "momentum": {
            "bands": [-1.01, -0.5, 0.0, 0.5, 1.01],
            "labels": ["<-0.5", "-0.5..0", "0..0.5", ">0.5"],
            "want": 1,
        },
        "structure": {
            "bands": [-1.01, -0.5, 0.5, 1.01],
            "labels": ["broken", "neutral", "constructive"],
            "want": 1,
        },
        "risk_oscillator": {
            "bands": [-0.01, 0.4, 0.6, 1.01],
            "labels": ["falling", "neutral", "rising"],
            "want": -1,
        },
    }
    if "bfi" in df.columns:
        SIGNALS["bfi"] = {"bands": [-0.1, 40, 60, 100.1],
                          "labels": ["<40", "40-60", ">60"], "want": 1}

    report: dict = {"meta": {"span": f"{df.index.min().date()}..{df.index.max().date()}",
                             "rows": len(df), "split": cfg["split_date"]},
                    "signals": {}, "risk_drawdown": {}, "allocation": {}, "whipsaw": {}}

    # Risk Index judged as a RISK gauge: forward drawdown by band (the correct
    # test — a working risk gauge precedes deeper drawdowns monotonically).
    rk_bands = [-0.1, 25, 50, 75, 100]
    rk_labels = ["0-25", "25-50", "50-75", "75-100"]
    ddt = {half: drawdown_table(df.loc[idx, "risk_index"], fdd.loc[idx],
                                rk_bands, rk_labels, horizons).to_dict("records")
           for half, idx in halves.items()}
    dd_col = f"avgDD_{horizons[0]}d"  # near-term: the right horizon for a risk gauge
    dd_full = rank_trend(pd.DataFrame(ddt["full"]), dd_col)
    dd_pre = rank_trend(pd.DataFrame(ddt["pre"]), dd_col)
    dd_post = rank_trend(pd.DataFrame(ddt["post"]), dd_col)
    if dd_full == -1 and dd_pre == -1 and dd_post == -1:
        ddt["verdict"] = f"CONFIRMED near-term risk gauge ({horizons[0]}d drawdown)"
    elif dd_full == -1:
        ddt["verdict"] = f"DIRECTIONAL near-term risk gauge ({horizons[0]}d; one half weak)"
    else:
        ddt["verdict"] = "CONTEXT-ONLY — rely on allocation drawdown reduction"
    ddt["rank_trend"] = {"full": dd_full, "pre": dd_pre, "post": dd_post, "want": -1,
                         "horizon": horizons[0]}
    report["risk_drawdown"] = ddt

    for sig, spec in SIGNALS.items():
        if sig not in df.columns:
            continue
        entry = {}
        for half, idx in halves.items():
            t = band_table(df.loc[idx, sig], fwd.loc[idx], spec["bands"], spec["labels"], horizons)
            entry[half] = t.to_dict("records")
        # robustness verdict on the 90d column via rank-trend (tolerant of one
        # noisy small-sample band; the long horizon is where signal separates)
        hcol = f"mean_{horizons[-1]}d"
        m_full = rank_trend(pd.DataFrame(entry["full"]), hcol)
        m_pre = rank_trend(pd.DataFrame(entry["pre"]), hcol)
        m_post = rank_trend(pd.DataFrame(entry["post"]), hcol)
        want = spec["want"]
        if m_full == want and m_pre == want and m_post == want:
            verdict = "CONFIRMED"
        elif m_full == -want:
            verdict = "INVERTED"
        elif m_full == want and (m_pre == want or m_post == want):
            verdict = "DIRECTIONAL (one half weak)"
        elif m_full == want:
            verdict = "DIRECTIONAL (full only)"
        else:
            verdict = "CONTEXT-ONLY"
        entry["verdict"] = verdict
        entry["monotone"] = {"full": m_full, "pre": m_pre, "post": m_post, "want": want}
        report["signals"][sig] = entry

    for variant in config.load()["vector"]["allocation"]["variants"]:
        col = f"alloc_{variant}"
        if col in df.columns:
            report["allocation"][variant] = backtest(close, df[col])

    for sig in ("momentum_state", "risk_regime", "structure_state", "market_mode", "alt_cycle_leader"):
        if sig in df.columns:
            report["whipsaw"][sig] = whipsaw(df[sig], cfg["whipsaw_max_days"])

    # ---- persist ----------------------------------------------------------- #
    outdir = config.data_dir() / "vector"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "calibration.json").write_text(json.dumps(report, indent=2, default=str))
    df.to_parquet(outdir / "signals.parquet")
    _write_markdown(report)
    print(_summary(report))
    return 0


def _summary(report: dict) -> str:
    L = [f"\n=== Bitcoin Vector calibration ({report['meta']['span']}, "
         f"{report['meta']['rows']} days) ==="]
    L.append("\nSIGNAL VERDICTS (forward-return monotonicity, split-half):")
    for sig, e in report["signals"].items():
        L.append(f"  {sig:16s} {e['verdict']:28s} monotone={e['monotone']}")
    L.append("\nForward-return by band (full sample):")
    for sig, e in report["signals"].items():
        L.append(f"  [{sig}]")
        for r in e["full"]:
            cols = "  ".join(f"{k}={r[k]}" for k in r if k not in ("band",))
            L.append(f"     {r['band']:16s} {cols}")
    if report.get("risk_drawdown"):
        rd = report["risk_drawdown"]
        L.append(f"\nRISK INDEX as a drawdown gauge: {rd['verdict']} "
                 f"(rank_trend={rd['rank_trend']})")
        L.append("  forward drawdown by risk band (full sample):")
        for r in rd["full"]:
            cols = "  ".join(f"{k}={r[k]}" for k in r if k not in ("band",))
            L.append(f"     {r['band']:10s} {cols}")
    L.append("\nALLOCATION BACKTEST vs HODL:")
    for v, m in report["allocation"].items():
        L.append(f"  {v:13s} CAGR {m['cagr']:>6}% (HODL {m['hodl_cagr']}%)  "
                 f"Sharpe {m['sharpe']} (HODL {m['hodl_sharpe']})  "
                 f"MaxDD {m['maxdd']}% (HODL {m['hodl_maxdd']}%)  "
                 f"inMkt {m['time_in_market']}%  xHODL {m['final_vs_hodl']}")
    L.append("\nWHIPSAW (state flips < max_days):")
    for s, w in report["whipsaw"].items():
        L.append(f"  {s:18s} {w['changes']:4d} changes, {w['pct']}% whipsaw")
    return "\n".join(L)


def _write_markdown(report: dict) -> None:
    m = report["meta"]
    lines = [f"# Bitcoin Vector — calibration report",
             "",
             f"Span: {m['span']} ({m['rows']} days). Split-half boundary: {m['split']}.",
             "",
             "House rule: a signal is trusted (labeled a *signal* in the UI) only if its "
             "forward outcome relationship trends in the expected direction in the full "
             "sample AND survives both halves (rank-trend |rho|>0.6, tolerant of one "
             "small-sample band). Return-predicting signals (momentum, structure, BFI) "
             "are judged on forward RETURN; the Risk Index is judged on forward DRAWDOWN "
             "(its actual job) because at long horizons extreme risk marks capitulation "
             "and forward *return* is U-shaped — the documented contrarian behavior, not "
             "a defect. Anything failing is context-only; anything inverted is flagged.",
             ""]
    lines.append("## Signal verdicts\n")
    lines.append("| Signal | Verdict | full | pre | post | want |")
    lines.append("|---|---|--:|--:|--:|--:|")
    for sig, e in report["signals"].items():
        mo = e["monotone"]
        lines.append(f"| {sig} | **{e['verdict']}** | {mo['full']} | {mo['pre']} "
                     f"| {mo['post']} | {mo['want']} |")
    if report.get("risk_drawdown"):
        rd = report["risk_drawdown"]
        lines.append(f"\n## Risk Index as a drawdown gauge\n")
        lines.append(f"**{rd['verdict']}** — rank-trend {rd['rank_trend']}.\n")
        lines.append(pd.DataFrame(rd["full"]).to_markdown(index=False))
    for sig, e in report["signals"].items():
        lines.append(f"\n### {sig} — forward returns by band (full sample)\n")
        t = pd.DataFrame(e["full"])
        lines.append(t.to_markdown(index=False))
    lines.append("\n## Allocation backtest vs HODL\n")
    cols = ["cagr", "hodl_cagr", "sharpe", "hodl_sharpe", "sortino", "hodl_sortino",
            "maxdd", "hodl_maxdd", "time_in_market", "final_vs_hodl"]
    at = pd.DataFrame(report["allocation"]).T[cols]
    lines.append(at.to_markdown())
    lines.append("\n## Whipsaw\n")
    wt = pd.DataFrame(report["whipsaw"]).T
    lines.append(wt.to_markdown())
    Path(config.load()["storage"]["reports_dir"], "vector-calibration.md").write_text(
        "\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
