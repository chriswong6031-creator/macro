"""FX decomposition for country_cycles (masterplan W3.9 / D4-W5b, D4 §5).

The country cycle page has always run its structure math on the **USD-listed ETF**
tape (EWJ, EWG, EWZ…).  That folds the *currency* cycle into every "equity cycle":
the audit's `cycle_dna.json` records EWJ fell 33% in USD in 2022 while Japanese
equities were roughly flat — the yen crash masquerading as a Japanese-equity trough.

This module resolves that conflation.  It constructs, per single-country ETF, the
**local-currency equity price series** (the honest "is this market's equity cheap"),
loads the **FX pair** as a separate first-class leg, and attributes each detected
turn's USD-tape move into an equity vs currency split (`fx_share`).

Construction (D4 §5.1), two paths, chosen per-market by MAX COVERAGE (D4-N4 — the
native local index is often SHORTER than the ETF, e.g. ^NSEI starts 2007 vs INDA's
deeper tape; blindly preferring the native index would silently truncate history):

  1. NATIVE local index  (^N225, ^GDAXI…) — the cleanest local-currency equity cycle
     (no ETF tracking error / fee drag / synthetic division) — used when its coverage
     over the ETF's own span is at least as long as the synthetic path.
  2. SYNTHETIC  P_local = P_usd_etf × FX_ccy_per_usd  — used when the native index is
     absent or SHORTER than the ETF span.

FX sign convention (verified empirically against the EWJ-2022 episode, see tests):
every pair is normalized to **CCY-per-USD** (the `USDxxx` convention; Yahoo pairs
quoted USD-per-CCY like EURUSD/GBPUSD/AUDUSD are inverted to 1/price).  Then

    P_local(t) = P_usd_etf(t) · FX_ccy_per_usd(t)

Intuition: when the yen weakens, USDJPY (yen-per-USD) RISES; a US holder of EWJ is
hurt by that, so the local-currency return is *better* (less negative) than the USD
return — multiplying the falling USD ETF by the rising USDJPY lifts it back toward the
flat local truth.  (The D4 §5.1 formula P_usd / FX is written for a USD-per-CCY quote;
with our CCY-per-USD store the operation is a multiply.  Tested both ways: multiply is
the one that reproduces ^N225.)

Blocs (EFA/VGK/VPL/EEM/AAXJ/ILF/VXUS) have no well-defined scalar FX without
time-varying holdings weights — they stay USD-only with a disclosed null-FX marker
(D4 §5.4).  Pure-read + additive: any failure on one market is logged and the country
falls back to USD-only, never fatal.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import store

log = logging.getLogger(__name__)

# ── FX share threshold: a turn whose USD move was >60% currency is "currency-driven"
#    (D4 §5.3 / masterplan R3 ruling — the flag that fires on the card).
FX_FLAG_THRESHOLD = 0.60

# ── per-country FX + local-index registry ───────────────────────────────────
# fx:      (group, ticker) of the FX parquet in the store.
# invert:  True when the stored pair quotes USD-per-CCY (EURUSD/GBPUSD/AUDUSD) so it
#          must be inverted to CCY-per-USD before the P_local = P_usd × FX multiply.
#          USDxxx pairs already quote CCY-per-USD → invert=False.
# local:   (group, ticker) of the NATIVE local-currency index parquet, or None.
# pair:    display label (the currency pair name).
# peg:     optional hard-peg band (HKD) → a peg-distance annotation, not a decomposition.
# fx_source: human-readable source string stamped onto the leg.
FX_REGISTRY: dict[str, dict] = {
    # ── Europe (EUR bloc pairs are USD-per-CCY → invert) ──
    "EWG": {"pair": "EURUSD", "fx": ("yahoo", "EURUSD_X"), "invert": True,
            "local": ("intl", "_GDAXI"), "fx_source": "yahoo:EURUSD_X"},
    "EWU": {"pair": "GBPUSD", "fx": ("yahoo", "GBPUSD_X"), "invert": True,
            "local": ("intl", "_FTSE"), "fx_source": "yahoo:GBPUSD_X"},
    "EWQ": {"pair": "EURUSD", "fx": ("yahoo", "EURUSD_X"), "invert": True,
            "local": ("intl", "_FCHI"), "fx_source": "yahoo:EURUSD_X"},
    "EWL": {"pair": "USDCHF", "fx": ("yahoo", "USDCHF_X"), "invert": False,
            "local": None, "fx_source": "yahoo:USDCHF_X"},
    "EWP": {"pair": "EURUSD", "fx": ("yahoo", "EURUSD_X"), "invert": True,
            "local": None, "fx_source": "yahoo:EURUSD_X"},
    "EWI": {"pair": "EURUSD", "fx": ("yahoo", "EURUSD_X"), "invert": True,
            "local": None, "fx_source": "yahoo:EURUSD_X"},
    "EWN": {"pair": "EURUSD", "fx": ("yahoo", "EURUSD_X"), "invert": True,
            "local": None, "fx_source": "yahoo:EURUSD_X"},
    "EWD": {"pair": "USDSEK", "fx": ("yahoo", "USDSEK_X"), "invert": False,
            "local": None, "fx_source": "yahoo:USDSEK_X"},
    # ── Developed ex-Europe ──
    "EWJ": {"pair": "USDJPY", "fx": ("yahoo", "USDJPY_X"), "invert": False,
            "local": ("intl", "_N225"), "fx_source": "yahoo:USDJPY_X"},
    "EWA": {"pair": "AUDUSD", "fx": ("yahoo", "AUDUSD_X"), "invert": True,
            "local": ("intl", "_AXJO"), "fx_source": "yahoo:AUDUSD_X"},
    "EWH": {"pair": "USDHKD", "fx": ("hk", "HKD_X"), "invert": False,
            "local": None, "peg": {"band": "7.75-7.85", "lo": 7.75, "hi": 7.85},
            "fx_source": "hk:HKD_X"},
    "EWS": {"pair": "USDSGD", "fx": ("yahoo", "USDSGD_X"), "invert": False,
            "local": None, "fx_source": "yahoo:USDSGD_X"},
    "EWC": {"pair": "USDCAD", "fx": ("yahoo", "USDCAD_X"), "invert": False,
            "local": None, "fx_source": "yahoo:USDCAD_X"},
    # ── EM Asia ──
    "FXI": {"pair": "USDCNH", "fx": ("yahoo", "CNH_F"), "invert": False,
            "local": None, "fx_source": "yahoo:CNH_F"},
    "INDA": {"pair": "USDINR", "fx": ("intl", "USDINR_X"), "invert": False,
             "local": ("intl", "_NSEI"), "fx_source": "intl:USDINR_X"},
    "EWT": {"pair": "USDTWD", "fx": ("intl", "USDTWD_X"), "invert": False,
            "local": ("intl", "_TWII"), "fx_source": "intl:USDTWD_X"},
    "EWY": {"pair": "USDKRW", "fx": ("intl", "USDKRW_X"), "invert": False,
            "local": ("intl", "_KS11"), "fx_source": "intl:USDKRW_X"},
    "EIDO": {"pair": "USDIDR", "fx": ("yahoo", "USDIDR_X"), "invert": False,
             "local": None, "fx_source": "yahoo:USDIDR_X"},
    # ── EM LatAm ──
    "EWZ": {"pair": "USDBRL", "fx": ("yahoo", "USDBRL_X"), "invert": False,
            "local": None, "fx_source": "yahoo:USDBRL_X"},
    "EWW": {"pair": "USDMXN", "fx": ("yahoo", "USDMXN_X"), "invert": False,
            "local": None, "fx_source": "yahoo:USDMXN_X"},
    "ECH": {"pair": "USDCLP", "fx": ("yahoo", "USDCLP_X"), "invert": False,
            "local": None, "fx_source": "yahoo:USDCLP_X"},
    # ── EM EMEA ──
    "EZA": {"pair": "USDZAR", "fx": ("yahoo", "USDZAR_X"), "invert": False,
            "local": None, "fx_source": "yahoo:USDZAR_X"},
    "TUR": {"pair": "USDTRY", "fx": ("yahoo", "USDTRY_X"), "invert": False,
            "local": None, "fx_source": "yahoo:USDTRY_X"},
    "EPOL": {"pair": "USDPLN", "fx": ("yahoo", "USDPLN_X"), "invert": False,
             "local": None, "fx_source": "yahoo:USDPLN_X"},
}


def _read_close(spec: tuple[str, str] | None) -> pd.Series | None:
    """Read a clean close series from a (group, ticker) store spec.

    FX pays no dividends, so the TR `close` column IS the price level (and it is the
    complete, gap-free one — the `close_price` backfill column on the FX parquets carries
    a one-day shift + NaN tail artifact, so we deliberately read `close`)."""
    if spec is None:
        return None
    df = store.read(spec[0], spec[1])
    if df is None or df.empty:
        return None
    col = "close" if "close" in df.columns else df.columns[0]
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index().dropna()


def fx_ccy_per_usd(meta: dict) -> pd.Series | None:
    """The FX pair normalized to CCY-per-USD (the USDxxx orientation).

    A rising series = the foreign currency WEAKENING vs the dollar (more CCY per USD).
    USD-per-CCY quotes (EURUSD/GBPUSD/AUDUSD, meta['invert']) are inverted to 1/price."""
    fx = _read_close(meta.get("fx"))
    if fx is None or fx.empty:
        return None
    if meta.get("invert"):
        fx = (1.0 / fx.replace(0.0, np.nan)).dropna()
    return fx.rename("fx_ccy_per_usd")


def build_local_series(ticker: str, fxmeta: dict, usd_px: pd.Series,
                       fx: pd.Series | None) -> tuple[pd.Series | None, str]:
    """Construct the LOCAL-currency equity price series + its `lc_source` label.

    D4 §5.1 + D4-N4 max-coverage chooser:
      * native local index used ONLY when its coverage over the ETF span ≥ the synthetic
        path's coverage (else it silently truncates the deep ETF history);
      * synthetic  P_local = P_usd_etf × FX_ccy_per_usd  otherwise.

    Returns (series, lc_source) where lc_source ∈ {'native','synthetic','none'}.
    `fxmeta` is the FX_REGISTRY entry (carries the native-index `local` spec).
    `usd_px` is the ETF price-basis series (structure basis)."""
    usd_px = usd_px.dropna()
    if usd_px.empty:
        return None, "none"
    etf_span = usd_px.index

    # synthetic candidate (needs the FX pair) — coverage = overlap with the ETF span.
    synth = None
    synth_cov = 0
    if fx is not None and not fx.empty:
        # sort=True pins the pre-pandas-4 default (sorted union index) explicitly.
        joined = pd.concat([usd_px.rename("px"), fx.rename("fx")], axis=1,
                           sort=True).dropna()
        if not joined.empty:
            synth = (joined["px"] * joined["fx"]).rename(ticker)
            synth_cov = int(synth.index.isin(etf_span).sum())

    # native candidate — coverage = its own overlap with the ETF span (the window that
    # actually gets plotted); a native index that starts AFTER the ETF loses that head.
    native = _read_close(fxmeta.get("local"))
    native_cov = 0
    if native is not None and not native.empty:
        native_cov = int(native.index[native.index.isin(etf_span)].size)
        # a native index need not be sampled on the exact ETF calendar; also credit its
        # raw span-overlap length so a clean daily index isn't unfairly penalised.
        span_overlap = native.loc[(native.index >= etf_span.min())
                                  & (native.index <= etf_span.max())]
        native_cov = max(native_cov, int(span_overlap.size))

    if native is not None and native_cov >= synth_cov and native_cov > 0:
        return native.rename(ticker), "native"
    if synth is not None and synth_cov > 0:
        return synth, "synthetic"
    if native is not None and native_cov > 0:
        return native.rename(ticker), "native"
    return None, "none"


def attribute_turn(p_local: pd.Series, p_usd: pd.Series, fx: pd.Series | None,
                   t_prev: pd.Timestamp, t_now: pd.Timestamp) -> dict | None:
    """Split the USD-ETF move over a turn's leg (t_prev→t_now) into equity vs FX (D4 §5.3).

        r_usd    = USD ETF return over the leg
        r_local  = local-currency equity return over the leg
        fx_leg   = r_usd - r_local   (residual = the FX contribution to the USD experience)
        fx_share = |fx_leg| / (|r_usd| + eps)   ∈ 0..1

    A leg with fx_share > 0.6 is "currency-driven": the USD move was mostly the currency,
    not the equity (the EWJ-2022 case → fx_share ≈ 1)."""
    def _lvl(s: pd.Series, t: pd.Timestamp) -> float | None:
        w = s[s.index <= t]
        return float(w.iloc[-1]) if len(w) else None

    lu0, lu1 = _lvl(p_usd, t_prev), _lvl(p_usd, t_now)
    ll0, ll1 = _lvl(p_local, t_prev), _lvl(p_local, t_now)
    if None in (lu0, lu1, ll0, ll1) or lu0 == 0 or ll0 == 0:
        return None
    r_usd = lu1 / lu0 - 1.0
    r_local = ll1 / ll0 - 1.0
    fx_leg = r_usd - r_local
    share = abs(fx_leg) / (abs(r_usd) + 1e-9)
    out = {
        "usd_leg_pct": round(r_usd * 100.0, 1),
        "equity_leg_pct": round(r_local * 100.0, 1),
        "fx_leg_pct": round(fx_leg * 100.0, 1),
        "fx_share": round(min(1.0, share), 3),
        "fx_flag": bool(share > FX_FLAG_THRESHOLD),
    }
    if fx is not None:
        rf0, rf1 = _lvl(fx, t_prev), _lvl(fx, t_now)
        if rf0 and rf1:
            out["fx_ccy_per_usd_leg_pct"] = round((rf1 / rf0 - 1.0) * 100.0, 1)
    return out


def peg_annotation(meta: dict, fx: pd.Series | None) -> dict | None:
    """HKD-style hard-peg distance annotation (D4 §5.4 / S4 §8) — for a pegged pair the
    FX contribution is ~0 except in peg-stress episodes, so we ship a band-distance read
    rather than a decomposition."""
    peg = meta.get("peg")
    if not peg or fx is None or fx.empty:
        return None
    last = float(fx.iloc[-1])
    lo, hi = peg["lo"], peg["hi"]
    mid = (lo + hi) / 2.0
    dist_bps = round((last - mid) / mid * 1e4, 1)
    return {"band": peg["band"], "level": round(last, 4), "dist_bps": dist_bps,
            "in_band": bool(lo <= last <= hi)}
