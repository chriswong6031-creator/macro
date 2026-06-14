"""Deribit public API collector (free, keyless).

- dvol: BTC implied-volatility index, daily OHLC since ~Mar 2021 (verified:
  2019 queries return empty). Chunked yearly requests handle the API's
  per-call point limits.
- options_structure: ONE call to get_book_summary_by_currency returns every
  listed BTC option (~950 instruments) with open_interest + mark_iv +
  underlying_price. From it we compute the full options-structure panel that
  Laevitas/CoinGlass sell (research/VECTOR_PROVIDER_RECON.md): ATM IV term
  structure (7/30/90/180d), 25-delta skew & risk reversal, put/call OI & volume
  ratios, max pain (front expiry), and a gamma-exposure estimate. Black-Scholes
  greeks are computed locally (scipy-free, r=0) — Deribit gives mark_iv per
  instrument, so delta/gamma are a closed-form transform, no extra calls.

  This is a POINT-IN-TIME snapshot (the chain has no history on the free API),
  stored one row/day and accumulating forward. Until ~6-12mo accrues it is
  CONTEXT/display only — never a calibration anchor (house rule). DVOL (deep
  history) and VRP (= DVOL - realized vol) are the calibratable options signals.

  GEX caveat: net dealer gamma needs an assumed dealer SIGN (the one genuinely
  proprietary piece). We use the common convention dealers long calls / short
  puts (call gamma +, put gamma -) and label it as an assumption.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import logging

import numpy as np
import pandas as pd

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)

SQRT2 = math.sqrt(2.0)
SQRT2PI = math.sqrt(2.0 * math.pi)


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def _npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT2PI


def _bs_delta_gamma(S: float, K: float, T: float, sigma: float, is_call: bool):
    """Black-Scholes delta & gamma, r=0 (crypto convention). Returns (delta, gamma)
    or (nan, nan) when inputs are degenerate."""
    if not (S > 0 and K > 0 and T > 0 and sigma > 0):
        return float("nan"), float("nan")
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * sqrtT)
    delta = _ncdf(d1) if is_call else _ncdf(d1) - 1.0
    gamma = _npdf(d1) / (S * sigma * sqrtT)
    return delta, gamma


def _parse_instrument(name: str):
    """'BTC-26MAR27-105000-C' -> (expiry_date, strike, is_call). None on parse fail."""
    try:
        _, exp, strike, kind = name.split("-")
        expiry = datetime.strptime(exp, "%d%b%y").replace(
            hour=8, tzinfo=timezone.utc)  # Deribit options expire 08:00 UTC
        return expiry, float(strike), (kind.upper() == "C")
    except Exception:
        return None


def _interp_iv_at_delta(deltas: list[float], ivs: list[float], target: float):
    """Interpolate IV at a target delta. deltas need not be sorted."""
    pairs = sorted((d, v) for d, v in zip(deltas, ivs) if np.isfinite(d) and np.isfinite(v))
    if len(pairs) < 2:
        return float("nan")
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    if target < xs[0] or target > xs[-1]:
        return float("nan")  # don't extrapolate the tail IV
    return float(np.interp(target, xs, ys))


def _skew_at_tenor(df: pd.DataFrame, S: float, target_d: float):
    """Normalized 25-delta skew + risk reversal at the expiry nearest target_d.
    Returns (rr_25d, skew_25d, tenor_d)."""
    exp = min(df["expiry"].unique(),
              key=lambda e: abs(df.loc[df["expiry"] == e, "tenor_d"].iloc[0] - target_d))
    ge = df[(df["expiry"] == exp) & (df["iv"] > 0)]
    if ge.empty:
        return None, None, None
    cc, pp = ge[ge["is_call"]], ge[~ge["is_call"]]
    iv_25c = _interp_iv_at_delta(cc["delta"].tolist(), cc["iv"].tolist(), 0.25)
    iv_25p = _interp_iv_at_delta(pp["delta"].tolist(), pp["iv"].tolist(), -0.25)
    atm_t = float(ge.loc[(ge["K"] - S).abs().idxmin(), "iv"])
    tenor = float(ge["tenor_d"].iloc[0])
    if np.isfinite(iv_25c) and np.isfinite(iv_25p) and atm_t:
        return iv_25c - iv_25p, (iv_25p - iv_25c) / atm_t, tenor
    return None, None, tenor


def compute_basis(rows: list[dict], now: datetime) -> dict:
    """Annualized FUTURES BASIS term structure (the leverage-demand curve our
    perp-funding signal is blind to). Steep contango = leveraged longs paying up
    (late-cycle froth); flat/backwardation = deleveraging/capitulation. Uses
    dated contracts >=20d to skip sub-week expiry noise."""
    out: dict = {}
    recs = []
    for r in rows:
        n = r.get("instrument_name", "")
        if n.endswith("PERPETUAL"):
            continue
        parts = n.split("-")
        if len(parts) < 2:
            continue
        try:
            exp = datetime.strptime(parts[1], "%d%b%y").replace(hour=8, tzinfo=timezone.utc)
        except ValueError:
            continue
        days = (exp - now).total_seconds() / 86400.0
        F = pd.to_numeric(r.get("mark_price"), errors="coerce")
        idx = pd.to_numeric(r.get("underlying_price") or r.get("estimated_delivery_price"),
                            errors="coerce")
        oi = pd.to_numeric(r.get("open_interest"), errors="coerce")
        if days > 0 and pd.notna(F) and pd.notna(idx) and idx > 0:
            recs.append({"days": days, "ann": (F / idx - 1) * (365 / days) * 100,
                         "oi": 0.0 if pd.isna(oi) else float(oi)})
    if not recs:
        return out
    d = pd.DataFrame(recs)
    liquid = d[d["days"] >= 20].sort_values("days")
    if liquid.empty:
        return out
    out["basis_front_ann"] = float(liquid.iloc[0]["ann"])           # nearest dated contract
    w = liquid["oi"]
    out["basis_ann"] = float((liquid["ann"] * w).sum() / w.sum()) if w.sum() > 0 else float(liquid["ann"].mean())
    far = liquid[liquid["days"] >= 80]
    if not far.empty:
        out["basis_slope"] = float(far.iloc[0]["ann"]) - out["basis_front_ann"]  # contango steepness
    return out


def _gamma_flip(df: pd.DataFrame, S: float):
    """Zero-gamma spot (dealer GEX sign-flip) + signed distance-to-flip. Recomputes
    the net dealer gamma across a ±25% spot grid using the stored per-strike K/T/IV
    (same closed form + assumed dealer sign as the GEX scalar), and finds the spot
    where it crosses zero, nearest to current spot. ABOVE flip = net long gamma
    (dealers dampen / pin / mean-revert); BELOW = net short (dealers amplify / trend) —
    a binary vol-regime BOUNDARY distinct from the per-1% sensitivity scalar.
    Snapshot-only (the chain has no free history) -> forward-accumulating context."""
    g = df.dropna(subset=["K", "T", "iv"])
    g = g[(g["iv"] > 0) & (g["oi"] > 0)]
    if len(g) < 20 or not (S > 0):
        return None, None, None
    K = g["K"].to_numpy(float)
    T = g["T"].to_numpy(float)
    sig = g["iv"].to_numpy(float) / 100.0
    oi = g["oi"].to_numpy(float)
    sgn = np.where(g["is_call"].to_numpy(bool), 1.0, -1.0)
    sqrtT = np.sqrt(T)
    grid = S * np.linspace(0.75, 1.25, 101)
    net = np.empty(len(grid))
    for i, Sx in enumerate(grid):
        d1 = (np.log(Sx / K) + 0.5 * sig * sig * T) / (sig * sqrtT)
        gamma = np.exp(-0.5 * d1 * d1) / SQRT2PI / (Sx * sig * sqrtT)
        net[i] = float(np.sum(sgn * gamma * oi * Sx * Sx * 0.01))
    flips = []
    for i in range(len(grid) - 1):
        if net[i] == 0.0 or (net[i] < 0) != (net[i + 1] < 0):
            x0, x1, y0, y1 = grid[i], grid[i + 1], net[i], net[i + 1]
            flips.append(x0 - y0 * (x1 - x0) / (y1 - y0) if y1 != y0 else x0)
    if not flips:
        regime = "long" if net[len(grid) // 2] >= 0 else "short"
        return None, None, regime
    flip = min(flips, key=lambda f: abs(f - S))
    return float(flip), round(100.0 * (S - flip) / S, 2), ("long" if S >= flip else "short")


def compute_structure(rows: list[dict], now: datetime, cfg: dict) -> dict:
    """Pure function (testable): chain rows -> structure-panel dict."""
    recs = []
    for r in rows:
        meta = _parse_instrument(r.get("instrument_name", ""))
        if meta is None:
            continue
        expiry, strike, is_call = meta
        T = (expiry - now).total_seconds() / (365.25 * 86400.0)
        if T <= 0:
            continue
        iv = pd.to_numeric(r.get("mark_iv"), errors="coerce")
        oi = pd.to_numeric(r.get("open_interest"), errors="coerce")
        vol = pd.to_numeric(r.get("volume"), errors="coerce")
        S = pd.to_numeric(r.get("underlying_price"), errors="coerce")
        recs.append({"expiry": expiry, "T": T, "K": strike, "is_call": is_call,
                     "iv": iv, "oi": 0.0 if pd.isna(oi) else float(oi),
                     "vol": 0.0 if pd.isna(vol) else float(vol),
                     "S": S, "tenor_d": T * 365.25})
    if not recs:
        return {}
    df = pd.DataFrame(recs)
    S = float(df["S"].median())
    out: dict = {"underlying": S, "total_oi_btc": float(df["oi"].sum())}

    # greeks (only where iv valid)
    sig = df["iv"] / 100.0
    dg = [_bs_delta_gamma(S, k, t, s, c)
          for k, t, s, c in zip(df["K"], df["T"], sig, df["is_call"])]
    df["delta"] = [d for d, _ in dg]
    df["gamma"] = [g for _, g in dg]

    # ---- put/call ratios ----
    calls, puts = df[df["is_call"]], df[~df["is_call"]]
    coi, poi = calls["oi"].sum(), puts["oi"].sum()
    cvol, pvol = calls["vol"].sum(), puts["vol"].sum()
    out["put_call_oi_ratio"] = float(poi / coi) if coi > 0 else None
    out["put_call_vol_ratio"] = float(pvol / cvol) if cvol > 0 else None

    # ---- ATM IV per expiry -> term structure ----
    atm_pts = []  # (tenor_days, atm_iv)
    for exp, g in df.groupby("expiry"):
        gv = g[g["iv"] > 0]
        if gv.empty:
            continue
        atm = gv.loc[(gv["K"] - S).abs().idxmin()]
        atm_pts.append((float(atm["tenor_d"]), float(atm["iv"])))
    atm_pts.sort()
    if atm_pts:
        ten = [p[0] for p in atm_pts]
        ivs = [p[1] for p in atm_pts]
        for d in cfg["term_tenors_d"]:
            key = f"atm_iv_{d}d"
            out[key] = (float(np.interp(d, ten, ivs))
                        if ten[0] <= d <= ten[-1] else None)
        a30 = out.get("atm_iv_30d")
        a90 = out.get("atm_iv_90d")
        out["term_slope_30_90"] = (a90 - a30) if (a30 and a90) else None

    # ---- 25-delta skew / risk reversal: main tenor + TERM STRUCTURE (7d vs 90d) ----
    rr30, sk30, t30 = _skew_at_tenor(df, S, cfg["skew_target_d"])
    out["rr_25d"], out["skew_25d"], out["skew_tenor_d"] = rr30, sk30, t30
    _, sk7, _ = _skew_at_tenor(df, S, 7)
    _, sk90, _ = _skew_at_tenor(df, S, 90)
    out["skew_25d_7d"], out["skew_25d_90d"] = sk7, sk90
    if sk7 is not None and sk90 is not None:
        out["skew_term"] = sk7 - sk90    # >0 = acute near-term fear vs calm structural

    # ---- max pain (the single highest-OI expiry) ----
    by_oi = df.groupby("expiry")["oi"].sum()
    if not by_oi.empty:
        front = by_oi.idxmax()
        fe = df[df["expiry"] == front]
        strikes = np.sort(fe["K"].unique())
        if len(strikes):
            payout = []
            for P in strikes:
                cpay = (fe.loc[fe["is_call"], "oi"] * (P - fe.loc[fe["is_call"], "K"]).clip(lower=0)).sum()
                ppay = (fe.loc[~fe["is_call"], "oi"] * (fe.loc[~fe["is_call"], "K"] - P).clip(lower=0)).sum()
                payout.append(cpay + ppay)
            out["max_pain"] = float(strikes[int(np.argmin(payout))])
            out["max_pain_expiry_d"] = float(fe["tenor_d"].iloc[0])

    # ---- gamma exposure (assumed dealer sign: long calls / short puts) ----
    sign = np.where(df["is_call"], 1.0, -1.0)
    g_usd = sign * df["gamma"].fillna(0) * df["oi"] * (S ** 2) * 0.01  # USD / 1% move
    out["gex_per_1pct_usd"] = float(g_usd.sum())
    out["gamma_concentration_usd"] = float((df["gamma"].fillna(0) * df["oi"] * (S ** 2) * 0.01).sum())
    # dealer gamma-FLIP level (zero-gamma spot) + signed distance-to-flip (D-vec-GAMMA)
    out["gamma_flip"], out["dist_to_flip_pct"], out["gamma_regime"] = _gamma_flip(df, S)
    return out


class DeribitAdapter(Adapter):
    name = "deribit"
    group = "deribit"
    stale_after_days = 3

    def __init__(self) -> None:
        self.cfg = config.load()["deribit"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        out = {}
        dv = self._dvol(full_history)
        if dv is not None:
            out["dvol"] = dv
        opt = self._options_structure()
        if opt is not None:
            out["options_structure"] = opt
        if not out:
            raise ValueError("deribit returned nothing")
        return out

    def _dvol(self, full_history: bool) -> pd.DataFrame | None:
        last = store.last_date(self.group, "dvol")
        if full_history or last is None:
            start = date.fromisoformat(self.cfg["dvol_earliest"])
        else:
            start = last - timedelta(days=3)
        end = date.today()
        frames = []
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=365), end)
            r = self.http_get(
                self.cfg["dvol_url"], retries=self.cfg["retries"],
                params={"currency": "BTC", "resolution": "86400",
                        "start_timestamp": str(int(datetime(cursor.year, cursor.month, cursor.day,
                                                            tzinfo=timezone.utc).timestamp() * 1000)),
                        "end_timestamp": str(int(datetime(chunk_end.year, chunk_end.month, chunk_end.day,
                                                          23, 59, tzinfo=timezone.utc).timestamp() * 1000))},
                timeout=30)
            data = (r.json().get("result") or {}).get("data") or []
            if data:
                df = pd.DataFrame(data, columns=["ts", "open", "high", "low", "close"])
                frames.append(df)
            cursor = chunk_end + timedelta(days=1)
        if not frames:
            return None
        allf = pd.concat(frames, ignore_index=True)
        allf["date"] = pd.to_datetime(allf["ts"], unit="ms").dt.normalize()
        allf = allf.set_index("date").sort_index()
        allf = allf[~allf.index.duplicated(keep="last")]
        return allf[["open", "high", "low", "close"]].rename(
            columns={c: f"dvol_{c}" for c in ["open", "high", "low", "close"]})

    def _options_structure(self) -> pd.DataFrame | None:
        r = self.http_get(self.cfg["options_url"], retries=self.cfg["retries"],
                          params={"currency": "BTC", "kind": "option"}, timeout=60)
        rows = r.json().get("result") or []
        if not rows:
            return None
        now = datetime.now(timezone.utc)
        struct = compute_structure(rows, now, self.cfg)
        if not struct:
            return None
        # futures basis term structure (one more call; merged into the snapshot)
        try:
            fr = self.http_get(self.cfg["options_url"], retries=self.cfg["retries"],
                               params={"currency": "BTC", "kind": "future"}, timeout=60)
            struct.update(compute_basis(fr.json().get("result") or [], now))
        except Exception as e:  # noqa: BLE001 — basis is a bonus; never fail the snapshot
            log.warning("deribit futures basis fetch failed: %s", e)
        today = pd.Timestamp(now.date())
        return pd.DataFrame({k: [v] for k, v in struct.items()}, index=[today])
