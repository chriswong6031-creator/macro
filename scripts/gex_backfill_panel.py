"""Decompress the OptionsDX EOD archives in data/gex_backfill/ ONCE into a cached,
source-AGNOSTIC daily GEX panel per symbol -> data/gex_backfill/panel_<sym>.parquet.

WHY THIS EXISTS: the panel schema below is the CONTRACT that both this volume-proxy
extractor AND a future Polygon (standing-OI) extractor emit, so the identical Phase-0
battery (scripts/gex_phase0.py) runs on the proxy history NOW and on real OI history
the moment Polygon lands — only the per-contract WEIGHT column changes (volume here,
open_interest for Polygon). That keeps the validation comparable across data sources.

HONEST LIMIT: OptionsDX EOD has NO open interest, so every gamma-exposure figure here
is weighted by call/put VOLUME — a FLOW proxy for standing dealer positioning, not the
definitive OI-GEX. First read (SPY/QQQ 2019-2023, scripts.research_gex_backfill): the
short-gamma -> higher-forward-RV claim shows NO EDGE on the proxy. This script makes
that test cheap to re-run and extends it to forward DRAWDOWN (see scripts/gex_phase0).

Daily panel columns (one row per quote-date, per symbol):
  date, symbol, spot, weight_kind, n_contracts,
  net_gex_bn   — dollarized net dealer GEX ($bn / 1% move) on +/-10% window, sign=long-call/short-put
  gamma_flip, dist_to_flip_pct, regime  — zero-gamma via +/-25% spot-grid re-eval (engine clone)
  call_wall, put_wall  — strike of max +gamma above / max -gamma below spot (+/-10%)
  atm_iv, put_skew_25  — ~30D ATM IV and (25-delta put IV - ATM IV) tail-pricing read

Run: .venv/bin/python -m scripts.gex_backfill_panel        (all symbols, skip cached)
     .venv/bin/python -m scripts.gex_backfill_panel --force qqq
"""
from __future__ import annotations

import glob
import logging
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SQRT2PI = np.sqrt(2.0 * np.pi)
WIN_NET = 0.10        # +/-10% of spot for the net-GEX / wall window (matches research proxy)
WIN_FLIP = 0.25       # +/-25% strike window feeding the zero-gamma grid (matches gex_engine)
GRID_PTS = 101        # spot-grid resolution for the flip
DTE_MAX = 365
MULT, PM, R = 100.0, 0.01, 0.043
Q = {"spx": 0.013, "spy": 0.013, "qqq": 0.006, "iwm": 0.013}
SKEW_DTE = (20, 45)   # expiry window for the 25-delta put-skew read

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("gex_backfill_panel")


def _vec_gamma(S_grid: np.ndarray, K: np.ndarray, T: np.ndarray, iv: np.ndarray, q: float) -> np.ndarray:
    """BS gamma for every contract (rows) at every hypothetical spot (cols). Vectorized
    clone of engine.greeks gamma so the flip is grid-reevaluated, not a naive per-strike
    sum at current spot."""
    K, T, iv = K[:, None], T[:, None], iv[:, None]
    S = S_grid[None, :]
    sqrtT = np.sqrt(T)
    d1 = (np.log(S / K) + (R - q + 0.5 * iv * iv) * T) / (iv * sqrtT)
    return np.exp(-q * T) * np.exp(-0.5 * d1 * d1) / SQRT2PI / (S * iv * sqrtT)


def _flip(K, T, iv, w, sign, spot, q):
    """Zero-gamma spot via a +/-25% grid reevaluation (engine.gex_engine._gamma_flip
    clone, vectorized). Returns (flip, signed dist-to-flip %, regime)."""
    if len(K) < 20 or not (spot > 0):
        return None, None, None
    grid = spot * np.linspace(0.75, 1.25, GRID_PTS)
    g = _vec_gamma(grid, K, T, iv, q)                       # [n_contracts, n_grid]
    net = (sign * w)[:, None] * g * MULT * grid[None, :] ** 2 * PM
    net = net.sum(axis=0)                                   # net $-gamma at each grid spot
    flips = []
    for i in range(len(grid) - 1):
        if net[i] == 0.0 or (net[i] < 0) != (net[i + 1] < 0):
            x0, x1, y0, y1 = grid[i], grid[i + 1], net[i], net[i + 1]
            flips.append(x0 - y0 * (x1 - x0) / (y1 - y0) if y1 != y0 else x0)
    if not flips:
        return None, None, ("long" if net[GRID_PTS // 2] >= 0 else "short")
    flip = min(flips, key=lambda f: abs(f - spot))
    return float(flip), round(100.0 * (spot - flip) / spot, 3), ("long" if spot >= flip else "short")


def reduce_chain(c: pd.DataFrame, spot: float, q: float) -> dict:
    """SOURCE-AGNOSTIC GEX core. `c` = one day's contracts in LONG form with columns
    K, T, iv, gamma, w, sign  (w = the dealer-positioning weight: open interest for a
    standing-OI source like Polygon, contract volume for the OptionsDX proxy; sign =
    +1 call / -1 put for the long-call/short-put dealer convention). Returns the net
    GEX, walls and grid zero-gamma flip. This is the ONLY function Polygon needs to
    reach — build the same `c` from an OI snapshot and the panel is identical in shape."""
    nm = c[c["K"].between(spot * (1 - WIN_NET), spot * (1 + WIN_NET))]
    dg = nm["sign"] * nm["gamma"] * nm["w"].fillna(0) * MULT * spot ** 2 * PM
    net_gex_bn = float(dg.sum() / 1e9)
    by_k = dg.groupby(nm["K"]).sum()
    up = by_k[by_k.index > spot]
    dn = by_k[by_k.index < spot]
    call_wall = float(up.idxmax()) if not up.empty and up.max() > 0 else None
    put_wall = float(dn.idxmin()) if not dn.empty and dn.min() < 0 else None
    fw = c[c["K"].between(spot * (1 - WIN_FLIP), spot * (1 + WIN_FLIP))]
    flip, dist, regime = _flip(fw["K"].to_numpy(float), fw["T"].to_numpy(float),
                               fw["iv"].to_numpy(float), fw["w"].fillna(0).to_numpy(float),
                               fw["sign"].to_numpy(float), spot, q)
    return {"net_gex_bn": round(net_gex_bn, 4),
            "gamma_flip": (round(flip, 2) if flip is not None else None),
            "dist_to_flip_pct": dist, "regime": regime,
            "call_wall": call_wall, "put_wall": put_wall}


def _reduce_day(g: pd.DataFrame, q: float) -> dict | None:
    """One OptionsDX quote-date chain -> one panel row (the volume-proxy adapter:
    normalizes OptionsDX wide columns into the long contract frame `reduce_chain`
    expects, then adds the ATM-IV / put-skew tail read)."""
    spot = float(g["UNDERLYING_LAST"].iloc[0])
    if not (spot and spot == spot and spot > 0):
        return None
    g = g[(g["DTE"] > 0) & (g["DTE"] <= DTE_MAX)]
    # stack calls and puts into the long contract table: K, T, iv, gamma, w(volume), sign
    rows = []
    for cp, sgn, iv_c, ga_c, vo_c in (("C", 1.0, "C_IV", "C_GAMMA", "C_VOLUME"),
                                      ("P", -1.0, "P_IV", "P_GAMMA", "P_VOLUME")):
        sub = g[["STRIKE", "DTE", iv_c, ga_c, vo_c]].copy()
        sub.columns = ["K", "DTE", "iv", "gamma", "w"]
        sub["sign"] = sgn
        rows.append(sub)
    c = pd.concat(rows, ignore_index=True)
    c["T"] = c["DTE"] / 365.0
    c = c[(c["iv"] > 0) & (c["w"].fillna(0) >= 0) & c["gamma"].notna() & c["K"].notna()]
    if len(c) < 20:
        return None

    core = reduce_chain(c, spot, q)

    # --- ATM IV (~30D) + 25-delta put skew (OptionsDX has per-contract delta + IV) ---
    atm_iv = put_skew = None
    exp = g[(g["DTE"] >= SKEW_DTE[0]) & (g["DTE"] <= SKEW_DTE[1])]
    if not exp.empty:
        dte_pick = exp.iloc[(exp["DTE"] - 30).abs().argmin()]["DTE"]
        e = exp[exp["DTE"] == dte_pick]
        atm = e.iloc[(e["STRIKE"] - spot).abs().argmin()]
        atm_iv = float(atm["C_IV"]) if atm["C_IV"] > 0 else (float(atm["P_IV"]) if atm["P_IV"] > 0 else None)
        ep = e[(e["P_DELTA"].notna()) & (e["P_IV"] > 0)]
        if not ep.empty and atm_iv:
            p25 = ep.iloc[(ep["P_DELTA"] + 0.25).abs().argmin()]
            put_skew = round(float(p25["P_IV"]) - atm_iv, 4)

    return {"spot": spot, "n_contracts": int(len(c)),
            "atm_iv": (round(atm_iv, 4) if atm_iv else None), "put_skew_25": put_skew, **core}


def _clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().strip("[]").upper() for c in df.columns]
    num = ["UNDERLYING_LAST", "STRIKE", "DTE", "C_GAMMA", "P_GAMMA", "C_VOLUME", "P_VOLUME",
           "C_IV", "P_IV", "C_DELTA", "P_DELTA"]
    for col in num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["QUOTE_DATE"], errors="coerce")
    return df


def _extract_symbol(sym: str) -> pd.DataFrame | None:
    archives = sorted(glob.glob(f"data/gex_backfill/{sym}_eod_*.7z"))
    if not archives:
        log.warning("%s: no archives", sym)
        return None
    import py7zr
    q = Q.get(sym, 0.0)
    rows = []
    for arc in archives:
        if os.path.getsize(arc) == 0:
            log.warning("  skip empty archive %s", os.path.basename(arc))
            continue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with py7zr.SevenZipFile(arc, "r") as z:
                    z.extractall(path=tmp)
                txts = sorted(glob.glob(os.path.join(tmp, "**", "*.txt"), recursive=True))
                for txt in txts:
                    chain = _clean_cols(pd.read_csv(txt, skipinitialspace=True))
                    for d, g in chain.dropna(subset=["date"]).groupby("date"):
                        row = _reduce_day(g, q)
                        if row:
                            row["date"] = d
                            rows.append(row)
                    del chain
            log.info("  %s: %d days so far", os.path.basename(arc), len(rows))
        except Exception as e:  # noqa: BLE001 — partial archive still useful
            log.warning("  skip corrupt archive %s: %s", os.path.basename(arc), e)
    if not rows:
        return None
    out = (pd.DataFrame(rows).drop_duplicates("date").set_index("date").sort_index())
    out["symbol"] = sym
    out["weight_kind"] = "volume"
    return out


def main(argv: list[str]) -> int:
    force = "--force" in argv
    syms = [a for a in argv if a in Q] or ["spy", "qqq", "spx"]
    for sym in syms:
        cache = Path(f"data/gex_backfill/panel_{sym}.parquet")
        if cache.exists() and not force:
            log.info("%s: cached (%s) — use --force to rebuild", sym, cache)
            continue
        log.info("%s: extracting...", sym)
        df = _extract_symbol(sym)
        if df is None or df.empty:
            log.warning("%s: no panel produced", sym)
            continue
        df.to_parquet(cache)
        span = f"{df.index.min().date()}..{df.index.max().date()}"
        nL, nS = int((df["regime"] == "long").sum()), int((df["regime"] == "short").sum())
        log.info("%s: wrote %s — %d days [%s], regime long=%d short=%d, net_gex mean=%.3f bn",
                 sym, cache, len(df), span, nL, nS, df["net_gex_bn"].mean())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
