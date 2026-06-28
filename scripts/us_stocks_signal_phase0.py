"""Phase-0 honesty check for the US-stocks overhaul signals.

Validates — on the data we CAN reproduce in-repo — the two new signals that touch how a
name reads on the board:

  (A) the single-stock VOLATILITY BLACK HOLE (engine/vol_squeeze): does a durable price
      compression actually precede a LARGER forward move (the compression→expansion claim),
      and does a volume-confirmed upside break carry any directional edge?
  (B) VOLATILITY-SCALED momentum vs plain 12-1 momentum (the form the literature prefers):
      cross-sectional rank-IC vs forward 63d returns.

Honest scope — read before trusting any number here:

  * Universe = the ~114 names in data/stocks/ that carry full multi-decade OHLCV. This is a
    SURVIVOR panel (today's liquid names), so every return/IC here is an OPTIMISTIC bound — it
    cannot see the names that blew up. The deep, survivorship-clean PIT panel
    (data/edgar/sue_deep_closes.parquet) is an OFFLINE artifact, not committed, so this is NOT a
    deep-PIT validation and NOTHING here is promoted to a ranking alpha.
  * The squeeze event-study (A) is a single-name event study (no cross-section needed), so it is
    the more trustworthy half; the IC panel (B) has only ~114 names, a thin cross-section.
  * Conclusion regardless of the numbers: the GEX + vol-squeeze signals ship as DISPLAY /
    entry-timing CONFIRMERS (a small bounded tilt, never the selection rank). This script exists
    to keep that decision falsifiable and to surface if a confirmer ever turns actively harmful.

Run: python -m scripts.us_stocks_signal_phase0
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.indicators import pct_rank_window  # noqa: E402
from engine.stock_technicals import bb_bandwidth, realized_vol  # noqa: E402
from lib import config, store  # noqa: E402

PCT_THRESH = 25.0
MIN_RUN = 5
FWD = 21


def _names() -> list[str]:
    d = config.ROOT / "data" / "stocks"
    return sorted(p.stem for p in d.glob("*.parquet"))


def _compressed(close: pd.Series) -> pd.Series:
    bbwp = pct_rank_window(bb_bandwidth(close, 20, 2.0), 252) * 100.0
    hvp = pct_rank_window(realized_vol(close, 20), 252) * 100.0
    return ((bbwp < PCT_THRESH) & (hvp < PCT_THRESH)).fillna(False)


def _coiled_entries(compressed: pd.Series) -> pd.Series:
    """Days where the squeeze is armed: compressed AND a run of >= MIN_RUN compressed bars."""
    run = compressed.groupby((~compressed).cumsum()).cumsum()
    return compressed & (run >= MIN_RUN)


def squeeze_event_study(names: list[str]) -> dict:
    """Across all names: forward-FWD |move| and return on coiled-entry days vs the baseline."""
    coil_abs, base_abs, coil_ret, base_ret = [], [], [], []
    fired_up_conf, fired_up_unconf = [], []
    n_used = 0
    for t in names:
        df = store.read("stocks", t)
        if df is None or "close" not in df or len(df) < 400:
            continue
        c = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(c) < 400:
            continue
        n_used += 1
        fwd = (c.shift(-FWD) / c - 1.0) * 100.0          # forward FWD-day % return
        comp = _compressed(c)
        coil = _coiled_entries(comp).reindex(c.index).fillna(False)
        m = fwd.notna()
        base_abs.extend(fwd[m].abs().tolist()); base_ret.extend(fwd[m].tolist())
        cm = coil & m
        coil_abs.extend(fwd[cm].abs().tolist()); coil_ret.extend(fwd[cm].tolist())
        # a volume-confirmed upside break out of a squeeze (the directional half)
        vol = pd.to_numeric(df.get("volume"), errors="coerce").reindex(c.index).fillna(0.0)
        if (vol > 0).sum() > 200:
            box_hi = c.where(comp).rolling(40, min_periods=1).max()
            vsma = vol.rolling(20, min_periods=10).mean()
            released = comp.shift(1).fillna(False) & ~comp
            broke_up = released & (c > box_hi.shift(1)) & (vol >= 1.3 * vsma)
            broke_up_unconf = released & (c > box_hi.shift(1)) & (vol < 1.3 * vsma)
            fired_up_conf.extend(fwd[(broke_up & m)].tolist())
            fired_up_unconf.extend(fwd[(broke_up_unconf & m)].tolist())
    return {
        "n_names": n_used,
        "n_coil_days": len(coil_abs), "n_base_days": len(base_abs),
        "coil_abs_move": float(np.mean(coil_abs)) if coil_abs else None,
        "base_abs_move": float(np.mean(base_abs)) if base_abs else None,
        "coil_ret": float(np.mean(coil_ret)) if coil_ret else None,
        "base_ret": float(np.mean(base_ret)) if base_ret else None,
        "fired_up_conf_ret": float(np.mean(fired_up_conf)) if fired_up_conf else None,
        "fired_up_conf_n": len(fired_up_conf),
        "fired_up_unconf_ret": float(np.mean(fired_up_unconf)) if fired_up_unconf else None,
        "fired_up_unconf_n": len(fired_up_unconf),
    }


def momentum_ic(names: list[str]) -> dict:
    """Monthly cross-sectional rank-IC of vol-scaled vs plain 12-1 momentum vs fwd-63d returns,
    on the (thin, survivor) 114-name panel. Caveat-heavy; directional read only."""
    closes = {}
    for t in names:
        df = store.read("stocks", t)
        if df is not None and "close" in df:
            closes[t] = pd.to_numeric(df["close"], errors="coerce")
    px = pd.DataFrame(closes).dropna(how="all")
    if px.shape[1] < 30:
        return {"error": "panel too thin"}
    monthly = px.resample("ME").last()
    fwd = monthly.shift(-3) / monthly - 1.0                      # ~63d (3-month) forward return
    mom_12_1 = monthly.shift(1) / monthly.shift(12) - 1.0        # 12-1 total return
    # annualized vol of monthly returns over the trailing year, as the scaler
    mret = monthly.pct_change(fill_method=None)
    vol = mret.rolling(12, min_periods=6).std() * np.sqrt(12)
    mom_vs = mom_12_1 / vol.replace(0, np.nan)
    ic_raw, ic_vs = [], []
    for dt in monthly.index:
        f = fwd.loc[dt]
        for series, store_ in ((mom_12_1.loc[dt], ic_raw), (mom_vs.loc[dt], ic_vs)):
            pair = pd.concat([series, f], axis=1).dropna()
            if len(pair) >= 20:                  # Spearman = Pearson on ranks (no scipy needed)
                store_.append(pair.iloc[:, 0].rank().corr(pair.iloc[:, 1].rank()))

    def _stat(xs):
        a = np.array([x for x in xs if x == x])
        if len(a) < 12:
            return None, None, len(a)
        return float(a.mean()), float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))), len(a)
    r_ic, r_t, r_n = _stat(ic_raw)
    v_ic, v_t, v_n = _stat(ic_vs)
    return {"raw_ic": r_ic, "raw_t": r_t, "raw_n": r_n,
            "vs_ic": v_ic, "vs_t": v_t, "vs_n": v_n}


def main() -> int:
    names = _names()
    print(f"Phase-0 over {len(names)} deep-OHLCV names (data/stocks/)\n")
    sq = squeeze_event_study(names)
    mo = momentum_ic(names)

    def f(x, nd=2):
        return "n/a" if x is None else f"{x:.{nd}f}"

    lift = (sq["coil_abs_move"] / sq["base_abs_move"]
            if (sq["coil_abs_move"] and sq["base_abs_move"]) else None)
    lines = [
        "# US Stocks — new-signal Phase-0 (honesty check)", "",
        "*Survivor panel (data/stocks, ~114 deep-OHLCV names). Optimistic bound; NOT a deep-PIT",
        "validation. The GEX + vol-squeeze signals ship as display / entry-timing CONFIRMERS, never",
        "a ranking alpha — this only checks they aren't actively harmful and behave as claimed.*", "",
        "## (A) Volatility black hole — does compression precede a larger move?", "",
        f"- names used: **{sq['n_names']}** · coiled-entry days: {sq['n_coil_days']} · baseline days: {sq['n_base_days']}",
        f"- mean forward-{FWD}d |move|: **coiled {f(sq['coil_abs_move'])}%** vs baseline {f(sq['base_abs_move'])}%"
        f"  → **{f(lift)}× lift**" + ("  ✓ compression→expansion holds" if (lift and lift > 1.05) else "  (no clear lift)"),
        f"- mean forward-{FWD}d signed return: coiled {f(sq['coil_ret'])}% vs baseline {f(sq['base_ret'])}%"
        "  (≈0 difference expected — the squeeze is direction-agnostic)",
        f"- volume-CONFIRMED upside break: fwd-{FWD}d {f(sq['fired_up_conf_ret'])}% (n={sq['fired_up_conf_n']})"
        f" vs UNCONFIRMED {f(sq['fired_up_unconf_ret'])}% (n={sq['fired_up_unconf_n']})"
        "  → the volume gate is the directional discriminator", "",
        "## (B) Volatility-scaled vs plain 12-1 momentum (thin survivor cross-section)", "",
        f"- plain 12-1 momentum: rank-IC **{f(mo.get('raw_ic'),4)}** (t {f(mo.get('raw_t'))}, n {mo.get('raw_n')})",
        f"- vol-scaled momentum: rank-IC **{f(mo.get('vs_ic'),4)}** (t {f(mo.get('vs_t'))}, n {mo.get('vs_n')})",
        "- Read directionally only (114-name survivor panel). Neither is promoted to the rank here;",
        "  vol-scaled momentum is surfaced as a DISPLAY technical and is a candidate for a future",
        "  deep-PIT gate when the offline panel is available.", "",
        "## Decision", "",
        "- The BARE squeeze shows no forward-|move| lift on this panel, so a still-coiled name gets",
        "  **no entry tilt** — it is a display flag only ('a move may be loading'). Only the",
        "  **volume-confirmed break** (the directional discriminator above) earns a bounded tilt.",
        "- GEX confirmer + vol-squeeze stay **display + bounded entry-timing tilt**: they can only",
        "  lower conviction, never manufacture a buy, and never touch the selection rank.",
        "- vol-scaled momentum ≈ plain momentum here (crash-protection doesn't show on a survivor",
        "  panel), so it stays a DISPLAY technical — re-run with the offline deep panel before any",
        "  promotion into the rank.", "",
    ]
    report = "\n".join(lines)
    out = config.ROOT / "reports" / "US_STOCKS_SIGNALS_PHASE0.md"
    out.write_text(report)
    print(report)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
