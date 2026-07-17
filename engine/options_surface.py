"""Whole-market dealer-surface aggregation engine — W2 SURFACE (RIC program).

Pure computation: for a (root, date) load greeks+oi from the ThetaData T1 store,
apply the OI[t−1] shift(1) law within each contract, and compute per-root daily
aggregates for the frozen W2 roster.

DEALER-SIGN PASSPORT (printed here as required by the masterplan + gex_engine audit #29)
  Convention (identical to engine/gex_engine.py):
    • Dealer is assumed LONG calls, SHORT puts.
    • GEX sign: call legs contribute +, put legs contribute −.
    • Same for VEX and CEX.
    This sign is an UNOBSERVABLE ASSUMPTION — it holds on average for index
    ETFs/indices based on dealer flow modeling, but it is NOT verified from
    position disclosures. Every consumer must print or display this caveat.
    For single-name roots the assumption is especially fragile (covered-call ETFs,
    retail call-buying). W2 covers index_etf / sector_etf / industry_etf ONLY
    (single_name is scope-fenced per masterplan §3 P2 Layer 2).

OI TIMING LAW (OPRA / LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE §8 ¶1):
    OPRA publishes OI once per day at ~06:30 ET representing EOD of the PREVIOUS
    trading day. So oi[t] represents positions as of EOD t−1. doi_series() in
    thetadata_store.py applies an additional shift(1) so that its day-t signal
    uses EOD t−2 positions (the OI parquet row dated t−1). aggregate_root_date()
    enforces the SAME convention: it loads the OI parquet row for the most recent
    date BEFORE date_str (i.e. oi dated t−1 = EOD t−2), matching doi_series exactly.
    compute_surface_row() itself is convention-agnostic — the caller is responsible
    for passing the correctly time-shifted oi_prev frame.

|·|-MAGNITUDE LAW:
    front7_abs_charm_share and front7_abs_gex_share use |·| (absolute value)
    to remain sign-agnostic and robust to the dealer-sign assumption uncertainty.
    The signed aggregates (net_gex_bn, net_vex, net_cex) carry the assumption
    caveat above.

ROOT CLASS MAPPING (frozen at audit date 2026-07-17):
    index_etf    : SPX, SPXW, SPY, QQQ, IWM, DIA
    sector_etf   : XLB, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY
    industry_etf : SMH, XBI, KRE

EXPIRY BUCKETS (calendar days from the quote date to expiration):
    front_week   : ≤ 7 calendar days
    front_month  : 8 – 35 calendar days
    back         : > 35 calendar days

OUTPUTS (one row per (root, date)):
    net_gex_bn            : net dealer gamma exposure, $ billion per 1% move
    net_vex               : net dealer vanna exposure ($ delta / 1 vol pt)
    net_cex               : net dealer charm exposure ($ delta / calendar day)
    front7_abs_charm_share: |CEX in front 7cd| / |total CEX|  (sign-robust)
    front7_abs_gex_share  : |GEX in front 7cd| / |total GEX|  (sign-robust)
    total_abs_gamma_notional : sum of unsigned $ gamma × OI × multiplier
    oi_notional           : sum of OI × strike × multiplier (total gamma notional proxy)
    root_class            : index_etf | sector_etf | industry_etf
    fw_gex_bn             : front-week net GEX ($ billion)
    fm_gex_bn             : front-month net GEX ($ billion)
    bk_gex_bn             : back net GEX ($ billion)
    fw_oi_frac            : fraction of total OI in front-week bucket
    fm_oi_frac            : fraction of total OI in front-month bucket
    dealer_sign_assumption: "long_call_short_put" — always printed, never omitted
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine.gex_engine import DEFAULTS
from engine.greeks import bs_greeks

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Root-class mapping (frozen: audit date 2026-07-17, 19 passing roots)
# XLC excluded — greeks/oi absent for 2017 (launched 2018-06-18)
# ---------------------------------------------------------------------------
ROOT_CLASS_MAP: dict[str, str] = {
    # index_etf
    "SPX":  "index_etf",
    "SPXW": "index_etf",
    "SPY":  "index_etf",
    "QQQ":  "index_etf",
    "IWM":  "index_etf",
    "DIA":  "index_etf",
    # sector_etf
    "XLB":  "sector_etf",
    "XLE":  "sector_etf",
    "XLF":  "sector_etf",
    "XLI":  "sector_etf",
    "XLK":  "sector_etf",
    "XLP":  "sector_etf",
    "XLRE": "sector_etf",
    "XLU":  "sector_etf",
    "XLV":  "sector_etf",
    "XLY":  "sector_etf",
    # industry_etf
    "SMH":  "industry_etf",
    "XBI":  "industry_etf",
    "KRE":  "industry_etf",
}

# Frozen surface roster (W2; audit date 2026-07-17)
SURFACE_ROSTER: list[str] = sorted(ROOT_CLASS_MAP.keys())

# Contract multiplier (equity/index options: 100 shares per contract)
_MULT = DEFAULTS["contract_multiplier"]   # 100.0
_PCT_MOVE = DEFAULTS["pct_move"]          # 0.01 (1% move scaling)

# Expiry bucket thresholds (calendar days)
FRONT_WEEK_MAX_CD = 7     # ≤ 7 cd
FRONT_MONTH_MAX_CD = 35   # 8–35 cd

# Dealer sign assumption string (always attached to every output frame)
DEALER_SIGN_ASSUMPTION = "long_call_short_put"


def _calendar_days(expiration_col: pd.Series, date_str: str) -> pd.Series:
    """Calendar days from date_str to each expiration. Returns float Series."""
    return (pd.to_datetime(expiration_col) - pd.Timestamp(date_str)).dt.days.astype(float)


def compute_surface_row(
    greeks_day: pd.DataFrame,
    oi_prev: pd.DataFrame,
    root: str,
    date_str: str,
) -> dict | None:
    """Compute one per-root daily surface aggregate row.

    Args:
        greeks_day : greeks tier rows for (root, date), columns:
                     expiration, strike, right, implied_vol, underlying_price
                     + optionally: delta, gamma, vanna, charm (vendor-provided;
                     but we RE-DERIVE from iv via bs_greeks exactly as gex_engine
                     does to maintain sign-comparable basis).
        oi_prev    : OI tier rows for (root, date−1) — the OI[t−1] shift already
                     applied by the caller (the builder loads oi at t−1 per the
                     timing law). Columns: expiration, strike, right, open_interest.
        root       : option root symbol (e.g. "SPY").
        date_str   : quote date "YYYY-MM-DD".

    Returns a dict of scalar aggregates, or None when the chain is too thin.

    DEALER-SIGN PASSPORT: this function uses the SAME sign convention as
    engine/gex_engine.compute_gex — dealer long call (sign +1) / short put (sign −1).
    This is an unobservable assumption; every downstream consumer must surface it.
    """
    if greeks_day is None or greeks_day.empty:
        return None
    if oi_prev is None or oi_prev.empty:
        return None

    root_class = ROOT_CLASS_MAP.get(root, "unknown")

    # ── join greeks to lagged OI ───────────────────────────────────────────────
    keys = ["expiration", "strike", "right"]
    g = greeks_day.copy()
    o = oi_prev[keys + ["open_interest"]].copy()

    # Normalise types for join
    g["expiration"] = g["expiration"].astype(str)
    o["expiration"] = o["expiration"].astype(str)
    g["strike"] = pd.to_numeric(g["strike"], errors="coerce")
    o["strike"] = pd.to_numeric(o["strike"], errors="coerce")
    g["right"] = g["right"].astype(str).str.upper()
    o["right"] = o["right"].astype(str).str.upper()

    m = g.merge(o, on=keys, how="inner")
    if m.empty:
        return None

    m = m[m["open_interest"] > 0].copy()
    if m.empty:
        return None

    # Require implied_vol and underlying_price
    m = m[m["implied_vol"].notna() & (m["implied_vol"] > 0)]
    if "underlying_price" not in m.columns or m["underlying_price"].isna().all():
        return None
    m = m[m["underlying_price"].notna() & (m["underlying_price"] > 0)]
    if m.empty:
        return None

    spot = float(m["underlying_price"].dropna().median())
    if not (spot > 0):
        return None

    # ── calendar days to expiry (used for expiry buckets) ────────────────────
    m["cd_to_exp"] = _calendar_days(m["expiration"], date_str)
    m = m[m["cd_to_exp"] >= 0].copy()   # drop already-expired

    # Time to expiry in years (for bs_greeks)
    m["T"] = m["cd_to_exp"] / 365.0
    m = m[m["T"] > 0].copy()
    if m.empty:
        return None

    # ── re-derive greeks via bs_greeks (same as gex_engine — sign-comparable) ─
    is_call = m["right"].eq("C")
    m["is_call"] = is_call

    try:
        greeks_out = [
            bs_greeks(spot, float(k), float(t), float(iv), bool(cc), 0.0, 0.0)
            for k, t, iv, cc in zip(m["strike"], m["T"], m["implied_vol"], m["is_call"])
        ]
    except Exception as e:  # noqa: BLE001
        log.warning("options_surface: bs_greeks failed for %s %s: %s", root, date_str, e)
        return None

    m["gamma"] = [g[1] for g in greeks_out]
    m["vanna"] = [g[2] for g in greeks_out]
    m["charm"] = [g[3] for g in greeks_out]   # per year; scale to per-day below

    # ── dealer-sign vector (PASSPORT: long call +1, short put −1) ────────────
    sign = np.where(m["is_call"], 1.0, -1.0)
    oi = m["open_interest"].astype(float).values

    # Unsigned $ gamma (level) — same as gex_engine
    dg = m["gamma"].values * oi * _MULT * (spot ** 2)

    # Signed aggregates ($ per 1% move for GEX; same scale as gex_engine)
    gex = sign * dg * _PCT_MOVE
    vex = sign * m["vanna"].values * oi * _MULT * spot * _PCT_MOVE
    cex = sign * (m["charm"].values / 365.0) * oi * _MULT * spot   # per calendar day

    m_idx = m.index
    m["gex"] = gex
    m["vex"] = vex
    m["cex"] = cex
    m["dg"]  = dg

    net_gex = float(m["gex"].sum())
    net_vex = float(m["vex"].sum())
    net_cex = float(m["cex"].sum())
    total_abs_gamma = float(m["dg"].sum())
    oi_notional = float((oi * m["strike"].values * _MULT).sum())

    # ── expiry bucket aggregates ──────────────────────────────────────────────
    fw = m[m["cd_to_exp"] <= FRONT_WEEK_MAX_CD]       # front-week ≤7cd
    fm = m[(m["cd_to_exp"] > FRONT_WEEK_MAX_CD)       # front-month 8–35cd
           & (m["cd_to_exp"] <= FRONT_MONTH_MAX_CD)]
    bk = m[m["cd_to_exp"] > FRONT_MONTH_MAX_CD]       # back >35cd

    fw_gex = float(fw["gex"].sum()) if not fw.empty else 0.0
    fm_gex = float(fm["gex"].sum()) if not fm.empty else 0.0
    bk_gex = float(bk["gex"].sum()) if not bk.empty else 0.0

    total_oi = float(oi.sum())
    fw_oi = float(fw["open_interest"].sum()) if not fw.empty else 0.0
    fm_oi = float(fm["open_interest"].sum()) if not fm.empty else 0.0

    fw_oi_frac = (fw_oi / total_oi) if total_oi > 0 else 0.0
    fm_oi_frac = (fm_oi / total_oi) if total_oi > 0 else 0.0

    # ── |·|-magnitude concentration shares (sign-robust, RUL-OVC-3) ─────────
    abs_gex_total = float(m["gex"].abs().sum())
    abs_cex_total = float(m["cex"].abs().sum())

    fw_abs_gex = float(fw["gex"].abs().sum()) if not fw.empty else 0.0
    fw_abs_cex = float(fw["cex"].abs().sum()) if not fw.empty else 0.0

    front7_abs_gex_share  = (fw_abs_gex / abs_gex_total) if abs_gex_total > 0 else 0.0
    front7_abs_charm_share = (fw_abs_cex / abs_cex_total) if abs_cex_total > 0 else 0.0

    return {
        "root":                     root,
        "date":                     date_str,
        "root_class":               root_class,
        "dealer_sign_assumption":   DEALER_SIGN_ASSUMPTION,
        # signed aggregates (assumption-dependent; passport printed above)
        "net_gex_bn":               round(net_gex / 1e9, 6),
        "net_vex":                  round(net_vex, 2),
        "net_cex":                  round(net_cex, 2),
        # |·|-magnitude concentration (sign-robust)
        "front7_abs_charm_share":   round(front7_abs_charm_share, 6),
        "front7_abs_gex_share":     round(front7_abs_gex_share, 6),
        # scale
        "total_abs_gamma_notional": round(total_abs_gamma, 2),
        "oi_notional":              round(oi_notional, 2),
        # expiry bucket breakdowns
        "fw_gex_bn":                round(fw_gex / 1e9, 6),
        "fm_gex_bn":                round(fm_gex / 1e9, 6),
        "bk_gex_bn":                round(bk_gex / 1e9, 6),
        "fw_oi_frac":               round(fw_oi_frac, 6),
        "fm_oi_frac":               round(fm_oi_frac, 6),
        # diagnostics
        "n_contracts":              int(len(m)),
        "spot":                     round(spot, 2),
    }


def aggregate_root_date(
    root: str,
    date_str: str,
    store_path: Path | str,
) -> dict | None:
    """High-level entry point: load greeks+oi for (root, date), apply OI[t−1] shift,
    and return compute_surface_row output.

    OI TIMING (doi_series convention):
        OPRA publishes the OI parquet for date t at ~06:30 ET, representing EOD t−1
        positions.  doi_series() applies an additional shift(1) so that its day-t
        signal uses the OI parquet row dated t−1 (= EOD t−2 positions).  This
        function enforces the SAME convention: it loads the OI parquet for the most
        recent available date STRICTLY BEFORE date_str.

        Concretely, for a signal dated "2023-06-15":
          • greeks  → date == "2023-06-15"  (close-of-t quotes)
          • oi_prev → date == "2023-06-14"  (most recent OI parquet < date_str,
                       which OPRA published 2023-06-14 morning = EOD 2023-06-13)
        This is one session fresher than available at start-of-session on 2023-06-15,
        but matches the frozen doi_series shift(1) law (RIC-R4/R5).

        The OI cross-year boundary (e.g. date_str = Jan-2 of year Y) is handled by
        also loading year Y−1 parquets so the previous trading day is reachable.
    """
    from engine.thetadata_store import _load_parquets, _normalise_date  # noqa: PLC0415

    store_path = Path(store_path)
    ts = pd.Timestamp(date_str)
    year = ts.year

    # Load greeks for the quote date
    greeks_all = _load_parquets("greeks", root, [year], store=store_path)
    if greeks_all.empty:
        return None
    greeks_all = _normalise_date(greeks_all)
    greeks_day = greeks_all[greeks_all["date"] == date_str]
    if greeks_day.empty:
        return None

    # Load OI — need the row for the PREVIOUS trading day (doi_series shift(1) law).
    # Load the current year; also load the prior year if date_str is early-January
    # so the Dec-31 row is reachable.
    oi_years = [year] if ts.month > 1 else [year - 1, year]
    oi_all = _load_parquets("oi", root, oi_years, store=store_path)
    if oi_all.empty:
        return None
    oi_all = _normalise_date(oi_all)

    # Select the most recent OI date STRICTLY before date_str (the shift(1) step)
    oi_before = oi_all[oi_all["date"] < date_str]
    if oi_before.empty:
        log.warning(
            "options_surface: no prior-day OI available for %s %s — skipping",
            root, date_str,
        )
        return None
    prev_date = oi_before["date"].max()
    oi_prev = oi_before[oi_before["date"] == prev_date]

    return compute_surface_row(
        greeks_day=greeks_day,
        oi_prev=oi_prev,
        root=root,
        date_str=date_str,
    )
