"""Cleaner volume-proxy GEX panel from massive.com 2-year history -> the SAME schema
as scripts/gex_backfill_panel, so scripts/gex_phase0 runs the identical battery on a
SECOND, independent, more-recent window (≈2024-2026, incl. the Aug-2024 vol spike).

WHY: massive has real OI only LIVE (no historical OI — tested). But its flat-file
day-aggregates give 2 years of per-contract daily CLOSE + VOLUME for every US option.
So we reconstruct a daily GEX panel by INVERTING Black-Scholes for IV from the option
closes (built off the reliable OTM wing per (strike,expiry) — ITM trade-closes are
stale/below-intrinsic), computing gamma, and weighting by VOLUME. Still a FLOW proxy
for standing OI (same honest limit as the OptionsDX backfill), but cleaner data, our
own IV, and a fresh out-of-window test of the short-gamma -> forward-vol/drawdown claim.

Forward OI accrual (the definitive test) is handled separately. This is the bridge.

Output: data/gex_backfill/panel_<sym>_massive.parquet (weight_kind='volume'), then
    .venv/bin/python -m scripts.gex_phase0 --suffix _massive --syms spy,qqq,iwm

Run: MASSIVE_API_KEY=... .venv/bin/python -m scripts.gex_massive_panel [--start 2024-06-20]
"""
from __future__ import annotations

import gzip
import io
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # massive cert chain doesn't verify

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.gex_backfill_panel import Q, SKEW_DTE, WIN_FLIP, reduce_chain  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("gex_massive_panel")

BASE = "https://api.massive.com"
SYMS = ("SPY", "QQQ", "IWM")          # liquid ETFs — clean spot; index SPX has no spot on this plan
R = 0.043
S3_PREFIX = "us_options_opra/day_aggs_v1"
SQRT2PI = np.sqrt(2.0 * np.pi)


# ---- vectorized BS price / IV-bisection / gamma / put-delta (no scipy) ----
def _ncdf(x):
    t = 1.0 / (1.0 + 0.2316419 * np.abs(x))
    d = 0.3989423 * np.exp(-x * x / 2.0)
    p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
    return np.where(x >= 0, 1.0 - p, p)


def _bs_px(S, K, T, sig, q, call):
    sig = np.maximum(sig, 1e-6); sqrtT = np.sqrt(T)
    d1 = (np.log(S / K) + (R - q + 0.5 * sig * sig) * T) / (sig * sqrtT); d2 = d1 - sig * sqrtT
    return np.where(call, S * np.exp(-q * T) * _ncdf(d1) - K * np.exp(-R * T) * _ncdf(d2),
                          K * np.exp(-R * T) * _ncdf(-d2) - S * np.exp(-q * T) * _ncdf(-d1))


def _iv(px, S, K, T, q, call, it=64):
    lo = np.full_like(px, 1e-3); hi = np.full_like(px, 5.0)
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        up = _bs_px(S, K, T, mid, q, call) < px            # price increasing in sigma
        lo = np.where(up, mid, lo); hi = np.where(up, hi, mid)
    return 0.5 * (lo + hi)


def _gamma(S, K, T, sig, q):
    sqrtT = np.sqrt(T)
    d1 = (np.log(S / K) + (R - q + 0.5 * sig * sig) * T) / (sig * sqrtT)
    return np.exp(-q * T) * np.exp(-0.5 * d1 * d1) / SQRT2PI / (S * sig * sqrtT)


def _put_delta(S, K, T, sig, q):
    sqrtT = np.sqrt(T)
    d1 = (np.log(S / K) + (R - q + 0.5 * sig * sig) * T) / (sig * sqrtT)
    return -np.exp(-q * T) * _ncdf(-d1)


def _sym_row(sub: pd.DataFrame, spot: float, q: float) -> dict | None:
    """One underlying's contracts on one day -> a panel row. IV from the OTM wing per
    (strike,expiry); gamma from that IV; weight = traded VOLUME; sign long-call/short-put."""
    piv = (sub.pivot_table(index=["K", "T"], columns="cp", values=["close", "volume"], aggfunc="first")
           .reset_index())
    piv.columns = ["K", "T", "C_close", "P_close", "C_vol", "P_vol"]
    piv = piv.fillna({"C_vol": 0.0, "P_vol": 0.0})
    if len(piv) < 20:
        return None
    otm_call = (piv["K"] >= spot).to_numpy()
    otm_close = np.where(otm_call, piv["C_close"], piv["P_close"]).astype(float)
    ok = np.isfinite(otm_close) & (otm_close > 0.02)
    piv = piv[ok].reset_index(drop=True); otm_call = otm_call[ok]; otm_close = otm_close[ok]
    if len(piv) < 20:
        return None
    Kk = piv["K"].to_numpy(float); Tt = piv["T"].to_numpy(float)
    iv = _iv(otm_close, spot, Kk, Tt, q, otm_call)
    good = (iv > 0.01) & (iv < 3.0)
    piv = piv[good].reset_index(drop=True); Kk, Tt, iv = Kk[good], Tt[good], iv[good]
    if len(piv) < 20:
        return None
    piv["iv"] = iv
    piv["gamma"] = _gamma(spot, Kk, Tt, iv, q)
    call_r = piv[["K", "T", "iv", "gamma"]].assign(w=piv["C_vol"], sign=1.0)
    put_r = piv[["K", "T", "iv", "gamma"]].assign(w=piv["P_vol"], sign=-1.0)
    c = pd.concat([call_r, put_r], ignore_index=True)
    core = reduce_chain(c, float(spot), q)

    # ATM IV (~30D) + 25-delta put skew, from the reconstructed surface
    atm_iv = put_skew = None
    dte = (Tt * 365).round()
    win = piv[(dte >= SKEW_DTE[0]) & (dte <= SKEW_DTE[1])].copy()
    if not win.empty:
        win["dte"] = (win["T"] * 365).round()
        epick = win.iloc[(win["dte"] - 30).abs().argmin()]["dte"]
        e = win[win["dte"] == epick]
        atm_iv = float(e.iloc[(e["K"] - spot).abs().argmin()]["iv"])
        puts = e[e["K"] < spot].copy()
        if not puts.empty and atm_iv:
            pd_ = _put_delta(spot, puts["K"].to_numpy(float), puts["T"].to_numpy(float),
                             puts["iv"].to_numpy(float), q)
            p25 = puts.iloc[int(np.abs(pd_ + 0.25).argmin())]
            put_skew = round(float(p25["iv"]) - atm_iv, 4)
    return {"spot": float(spot), "n_contracts": int(len(c)),
            "atm_iv": (round(atm_iv, 4) if atm_iv else None), "put_skew_25": put_skew, **core}


def _closes(sym: str, start: str, end: str) -> dict:
    r = requests.get(f"{BASE}/v2/aggs/ticker/{sym}/range/1/day/{start}/{end}",
                     params={"adjusted": "true", "limit": 50000, "apiKey": os.environ["MASSIVE_API_KEY"]},
                     timeout=40, verify=False).json()
    return {pd.Timestamp(x["t"], unit="ms").normalize(): float(x["c"]) for x in r.get("results", [])}


def _day(s3, dstr: str, spots: dict) -> list[dict]:
    """Download one day's OPRA aggregates, build a panel row per underlying."""
    y, mo = dstr[:4], dstr[5:7]
    key = f"{S3_PREFIX}/{y}/{mo}/{dstr}.csv.gz"
    try:
        raw = gzip.decompress(s3.get_object(Bucket=os.environ["MASSIVE_S3_BUCKET"], Key=key)["Body"].read())
    except Exception as e:  # noqa: BLE001 — missing day / 403 boundary
        log.debug("skip %s: %s", dstr, str(e)[:60])
        return []
    df = pd.read_csv(io.BytesIO(raw), usecols=["ticker", "volume", "close"])
    out = []
    ts = pd.Timestamp(dstr)
    for sym in SYMS:
        spot = spots.get(sym, {}).get(ts)
        if not spot:
            continue
        sub = df[df["ticker"].str.startswith(f"O:{sym}2")].copy()
        if len(sub) < 40:
            continue
        m = sub["ticker"].str.extract(rf"^O:{sym}(?P<exp>\d{{6}})(?P<cp>[CP])(?P<strike>\d{{8}})$")
        sub = sub.join(m).dropna(subset=["exp", "cp", "strike"])
        sub["K"] = pd.to_numeric(sub["strike"]) / 1000.0
        sub["T"] = (pd.to_datetime(sub["exp"], format="%y%m%d") - ts).dt.days / 365.0
        sub = sub[(sub["T"] > 2 / 365) & (sub["K"].between(spot * (1 - WIN_FLIP), spot * (1 + WIN_FLIP)))]
        row = _sym_row(sub, spot, Q.get(sym.lower(), 0.0))
        if row:
            row.update({"date": ts, "symbol": sym.lower(), "weight_kind": "volume"})
            out.append(row)
    return out


def main(argv: list[str]) -> int:
    if "MASSIVE_API_KEY" not in os.environ:
        log.error("set MASSIVE_API_KEY (source .env)"); return 1
    import boto3
    start = argv[argv.index("--start") + 1] if "--start" in argv else \
        (pd.Timestamp.today() - pd.Timedelta(days=725)).strftime("%Y-%m-%d")
    end = pd.Timestamp.today().strftime("%Y-%m-%d")
    spots = {s: _closes(s, start, end) for s in SYMS}
    days = sorted({d for s in SYMS for d in spots[s]})
    days = [d.strftime("%Y-%m-%d") for d in days]
    log.info("massive panel: %d trading days %s..%s, syms=%s", len(days), days[0], days[-1], SYMS)
    from botocore.config import Config
    s3 = boto3.client("s3", endpoint_url=os.environ["MASSIVE_S3_ENDPOINT"],
                      aws_access_key_id=os.environ["MASSIVE_S3_ACCESS_KEY_ID"],
                      aws_secret_access_key=os.environ["MASSIVE_S3_SECRET_ACCESS_KEY"],
                      config=Config(max_pool_connections=16))
    rows = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(_day, s3, d, spots): d for d in days}
        done = 0
        for f in as_completed(futs):
            rows.extend(f.result()); done += 1
            if done % 50 == 0:
                log.info("  %d/%d days, %d rows", done, len(days), len(rows))
    if not rows:
        log.error("no rows built"); return 1
    panel = pd.DataFrame(rows)
    for sym in SYMS:
        d = panel[panel["symbol"] == sym.lower()].drop_duplicates("date").set_index("date").sort_index()
        if d.empty:
            continue
        cache = Path(f"data/gex_backfill/panel_{sym.lower()}_massive.parquet")
        d.to_parquet(cache)
        nL = int((d["regime"] == "long").sum()); nS = int((d["regime"] == "short").sum())
        log.info("%s: wrote %s — %d days [%s..%s], long=%d short=%d, net_gex mean=%.2f bn",
                 sym, cache, len(d), d.index.min().date(), d.index.max().date(), nL, nS, d["net_gex_bn"].mean())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
