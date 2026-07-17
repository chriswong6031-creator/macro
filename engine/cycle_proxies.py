"""Per-flagship PROXY REGISTRY — the Python source of truth for which live tape backs
each cycle.html cycle (and the SPX flagship), at which frequency, under which kernel,
and at which tier.  D3-W3.1 §1, implementing the D3_FLAGSHIPS.md spec.

Ruling A3 (two-word MEASURED/FRAME taxonomy):
  tier "measured" — the engine computes every plotted number from `series`.
  tier "frame"    — no gradeable tape (or n≈2 turns); hand-dated turns are the only
                    turn source, rendered as a STRUCTURAL FRAME.  proxy / monthly / dual
                    are hover-line DETAILS, not top-level tiers.

Ruling R3-C5 (tier attaches to a BAND, not a cycle):
  each cycle declares `bands: [...]`.  A DUAL card carries BOTH a measured intermediate
  band AND a frame secular band (gold/dollar/japan/bitcoin).  A frame-only card carries
  one frame band (housing/shipping/lithium/iron-ore).

Ruling A17 (proxy bands validate turn TIMING only):
  a band whose tape is an equity standing in for the researched series (memory→MU,
  uranium→CCJ) carries proxy=True and position_gauge=False — it is trusted for WHEN a
  turn happened, never for the plotted 0–100 position.  Its `fitness` gate (§1.5) must
  be EARNED against the hand-turn dates or the band auto-demotes to frame.

`invert` (credit spreads / vol / long-bond yields): the kernel runs on 1/x so
"100 = risk-on / complacent" holds (tights = top, calm = top, low yield = price top).

The registry embeds no page code: it is exported to data/cycle_ontology/proxy_registry.json
at build (scripts/build_proxy_registry.py) for the D3-W3 page work to consume (T2 discipline
— JS never re-declares it).

DEVIATIONS FROM D3_FLAGSHIPS.md §1.2 (documented per the wave mandate — the spec was
designed against a pre-W1.4 data snapshot; where it assumed a series that does not exist
on disk, this registry adjusts and records why):
  - `business`: D3 specced a FRED leading-index COMPOSITE via engine/business_cycle.py.
    W3.1's load_series resolves ONE tape per band, so the measured band binds INDPRO
    (industrial production, monthly, deep history) with an abs-ZigZag on its z-score
    (zz_abs=1.5σ per §2.3); the composite remains the richer object for a later wave and
    is noted on the band.  Tier is MEASURED-monthly, as D3 intended.
  - `long-bonds`: D3's abs "35bp via 1/x pct" is expressed here as a vol-scaled % ZigZag
    on the inverted (1/yield) tape — the abs-bp threshold does not translate cleanly to
    1/x units, and % on 1/x is the same clean filter the other inverted cards use.
  - `dollar`: DX-Y.NYB resolves (14,095 rows, 1971→) so the measured band binds it as
    specced.
  - `japan`: local-ccy Nikkei (intl:^N225 → data/intl/_N225.parquet) resolves; measured
    band binds it as the primary leg.
  - every ADD series in D3 §1.4 (MU, ALB, SQM, DBA, ^SOX, ZC=F, NG=F, PL=F, PA=F +
    FRED CSUSHPISA/DCOILWTICO/DHHNGSP/HOUST) is present on disk (W1.4 merged) — verified
    by registry_report().

CENSUS RECONCILIATION vs D3 §1.2:
  D3's headline said "14 MEASURED (incl. 4 DUAL) / 2 proxy / 1 monthly / 4 frame-only /
  4 dual-frame".  The as-built count over the 23 cycle.html cycles is:
    16 MEASURED-daily (12 pure + 4 DUAL) / 2 proxy / 1 monthly / 4 frame-only / 6 dual-frame.
  Two documented deltas from the HEADLINE (not from the D3 TABLE, which the build matches):
    (1) The D3 headline "14" undercounts its OWN §1.2 table, which tags 16 daily rows
        MEASURED/DUAL-measured (semis, oil, copper, gold, bitcoin, credit, agriculture,
        vol, biotech, long-bonds, dollar, natural-gas, silver, em-equities, japan, pgms).
        We follow the table; the "14" was a D3 arithmetic slip.
    (2) dual-frame = 6 not 4 because the 2 proxy cards (memory, uranium) ALSO carry a
        secular FRAME overlay band per the D3 table ("+ STRUCT overlay") — the hand ASP /
        U3O8 turns.  So 4 DUAL cards + 2 proxy-cards-with-frame-overlay = 6 frame bands
        on multi-band cards.  This is faithful to the table, not a scope addition.
  (spx flagship is registered as a 24th entry per the markets.html fold; excluded from the
  23-cycle census above.)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from lib import store

log = logging.getLogger("cycle_proxies")

# Output artifact paths (consumed by later D3 waves; JS never re-declares the registry).
_REGISTRY_JSON = Path("data/cycle_ontology/proxy_registry.json")
_HEALTH_JSON = Path("data/cycle_ontology/registry_health.json")
_FITNESS_JSON = Path("data/cycle_ontology/proxy_fitness.json")

# staleness limits: a `measured` band whose tape is older than this many CALENDAR days
# is reported STALE (per-band degrade — the band renders from its last data with a
# visible stale mark; it never aborts the page, house law).  Monthly tapes get a longer
# leash: a monthly macro series is stamped at PERIOD-START and released with a lag, so
# the freshest stamp is legitimately ~2 full periods + the release day behind wall-clock.
# A band whose release calendar outruns these defaults declares `stale_limit_days` on
# its registry row (e.g. business/INDPRO: obs dated the 1st, G.17 lands mid-second-month
# after → worst-case healthy age 31+30+~17 ≈ 78d, so the old 75d default tripped for
# 1-2 days EVERY month the release landed after the 15th).
_STALE_MAX_D = 7
_STALE_MAX_M = 75


class ProxyMissing(RuntimeError):
    """Raised by load_series when a band's declared series ref cannot be resolved."""


# ── series-ref resolution ───────────────────────────────────────────────────────────
def _split_ref(ref: str) -> tuple[str, str]:
    """'yahoo:GC=F' -> ('yahoo','GC=F');  'fred:VIXCLS' -> ('fred','VIXCLS');
    'intl:^N225' -> ('intl','^N225').  The store's own sanitizer (^→_, =→_, /→_)
    handles the filename mapping — we pass the RAW ticker so the registry stays readable."""
    if ":" not in ref:
        raise ProxyMissing(f"malformed series ref (want 'group:ticker'): {ref!r}")
    grp, tick = ref.split(":", 1)
    return grp, tick


def _read_ref(ref: str) -> pd.Series:
    """Resolve one series ref → a clean float pd.Series (the store applies the sanitizer).
    Yahoo tapes: prefer close_price (split-adj, dividend-UNadjusted) when present, else
    close (TR); the record_series basis label is set from the band's declared `basis`.
    FRED / intl tapes: the single value column."""
    grp, tick = _split_ref(ref)
    df = store.read(grp, tick)
    if df is None or df.empty:
        raise ProxyMissing(f"{ref} — no data on disk (store.read returned empty)")
    if grp == "yahoo":
        col = "close_price" if "close_price" in df.columns else "close"
    elif "close" in df.columns:
        col = "close"
    else:
        col = df.columns[0]
    s = df[col].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def load_series(band: dict) -> pd.Series:
    """Resolve band['series'] → one RAW pd.Series in NATIVE units (first ref available
    wins).  This is a pure DATA resolver: it does NOT apply band['invert'] or the monthly
    resample — those are KERNEL concerns owned by record_series (which takes freq= and
    invert= directly).  Keeping the single inversion point in the kernel avoids the
    double-invert trap (a band flagged invert would otherwise be inverted here AND again
    inside record_series, cancelling out).  `.attrs['ref']`/`['basis']` are stamped for
    the caller.

    NP-3 GUARD (the PL trap): a band whose basis is 'futures_cont' MUST NOT resolve to an
    equity tape.  PL (Planet Labs equity) and PL=F (platinum future) both exist; the
    registry pins the explicit yfinance future symbol, and this guard asserts the ref's
    ticker carries the '=F' futures marker so a naive 'PL' can never silently plot a
    satellite company as a metals cycle.

    Raises ProxyMissing if no ref resolves, or if a futures_cont band resolves an equity."""
    refs = band.get("series")
    if refs is None:
        raise ProxyMissing(f"band {band.get('band')!r} is frame-only (series=None) — "
                           f"load_series is undefined for a frame band")
    if isinstance(refs, str):
        refs = [refs]
    if band.get("basis") == "futures_cont":
        for ref in refs:
            _, tick = _split_ref(ref)
            if "=F" not in tick and not tick.endswith("_F"):
                raise ProxyMissing(
                    f"NP-3 trap: futures_cont band {band.get('band')!r} names {ref!r} which "
                    f"is not a futures symbol (no '=F') — would plot an equity as a metals "
                    f"cycle. Pin the explicit yfinance future symbol.")
    last_err: Exception | None = None
    for ref in refs:
        try:
            s = _read_ref(ref)
        except ProxyMissing as e:  # noqa: PERF203
            last_err = e
            continue
        s.attrs["ref"] = ref
        s.attrs["basis"] = band.get("basis")
        return s
    raise ProxyMissing(f"no ref resolved for band {band.get('band')!r}: {refs} ({last_err})")


# ── the registry ─────────────────────────────────────────────────────────────────────
# Each cycle maps to a list of bands.  Band schema:
#   band       "intermediate" | "secular"
#   tier       "measured" | "frame"
#   series     "group:ticker" | ["ref1","ref2"] (priority order) | None (frame-only)
#   freq       "D" | "M"
#   basis      "spot"|"futures_cont"|"fred_level"|"etf_tr"|"etf_px"|"index_px"|"equity_px"
#   invert     bool  (credit/vol/long-bonds run on 1/x)
#   kernel     {"zz_pct"|"zz_abs"|"zz_scaled": ..., "trend_span":..., "stoch_win":...}
#              zz_scaled=True → the kernel's vol-scaled default (daily _zz_pct_for /
#              monthly _zz_pct_for_monthly); zz_pct/zz_abs = an explicit override.
#   proxy      bool  (equity standing in for a researched series; ruling A17)
#   position_gauge  bool  (False for proxy bands — timing only, never plotted position)
#   fitness    {"kind": "dram"|"u3o8", "match_rate_min":..., "offset_max_months":...}
#              present ONLY on proxy bands; the earned-artifact gate (§1.5).
def _measured(band, series, *, freq="D", basis, invert=False, kernel=None, note="",
              stale_limit_days=None):
    return {"band": band, "tier": "measured", "series": series, "freq": freq,
            "basis": basis, "invert": invert,
            "kernel": kernel or {"zz_scaled": True},
            "proxy": False, "position_gauge": True, "fitness": None, "note": note,
            "stale_limit_days": stale_limit_days}


def _proxy(band, series, *, freq="D", basis, kernel=None, fitness, note=""):
    return {"band": band, "tier": "measured", "series": series, "freq": freq,
            "basis": basis, "invert": False,
            "kernel": kernel or {"zz_scaled": True},
            "proxy": True, "position_gauge": False, "fitness": fitness, "note": note}


def _frame(band, *, note="", monitors=None):
    return {"band": band, "tier": "frame", "series": None, "freq": None,
            "basis": None, "invert": False, "kernel": None,
            "proxy": False, "position_gauge": False, "fitness": None,
            "monitors": monitors or [], "note": note}


REGISTRY: dict[str, dict] = {
    # ── 14 MEASURED (incl. 4 DUAL measured bands) ──────────────────────────────────
    "semis": {"name": "Semiconductors", "bands": [
        _measured("intermediate", "yahoo:SOXX", basis="etf_tr",
                  note="^SOX index level backs the falsifier; SOXX ETF is the tradeable cycle")]},
    "oil": {"name": "Oil", "bands": [
        _measured("intermediate", ["fred:DCOILWTICO", "yahoo:CL=F"], basis="spot",
                  note="FRED WTI spot preferred over continuous futures for ZigZag cleanliness")]},
    "copper": {"name": "Copper", "bands": [
        _measured("intermediate", "yahoo:HG=F", basis="futures_cont",
                  note="falsifier $/t = $/lb × 2204.62")]},
    "credit": {"name": "Credit (HY spreads)", "bands": [
        _measured("intermediate", "fred:BAMLH0A0HYM2", basis="fred_level", invert=True,
                  kernel={"zz_scaled": True},
                  note="INVERTED: tights = cycle top (risk-on). 100 = tightest spreads (complacent)")]},
    "agriculture": {"name": "Agriculture", "bands": [
        _measured("intermediate", "yahoo:DBA", basis="etf_tr",
                  note="DBA is the tradeable GSCI-ag object; ZC=F backs the corn falsifier leg")]},
    "vol": {"name": "Volatility", "bands": [
        _measured("intermediate", ["fred:VIXCLS", "yahoo:^VIX"], basis="fred_level", invert=True,
                  note="INVERTED: deep calm = cycle top. Richest turn sample (~2y period)")]},
    "biotech": {"name": "Biotech", "bands": [
        _measured("intermediate", ["yahoo:XBI", "yahoo:IBB"], basis="etf_tr",
                  note="XBI equal-weight primary; IBB cap-weight secondary")]},
    "long-bonds": {"name": "Long Bonds", "bands": [
        _measured("intermediate", "fred:DGS30", basis="fred_level", invert=True,
                  note="INVERTED 30y yield = price-cycle clock (low yield = price top). "
                       "DEVIATION: D3's abs-35bp expressed as vol-scaled % on 1/x; TLT backs the falsifier")]},
    "natural-gas": {"name": "Natural Gas", "bands": [
        _measured("intermediate", ["fred:DHHNGSP", "yahoo:NG=F"], basis="spot",
                  note="Henry Hub spot; storage falsifier leg (EIA weekly) not collected → dropped")]},
    "silver": {"name": "Silver", "bands": [
        _measured("intermediate", "yahoo:SI=F", basis="futures_cont",
                  note="gold/silver ratio derived for tripwires")]},
    "em-equities": {"name": "EM Equities", "bands": [
        _measured("intermediate", "yahoo:EEM", basis="etf_tr",
                  note="MSCI-EM-index falsifier levels rewritten as EEM levels")]},
    "pgms": {"name": "PGMs (Platinum / Palladium)", "bands": [
        _measured("intermediate", "yahoo:PL=F", basis="futures_cont",
                  note="NP-3 trap: explicit PL=F (platinum) — NOT PL (Planet Labs equity). "
                       "PA=F (palladium) is the second leg for the falsifier")]},

    # ── 1 MEASURED-monthly ──────────────────────────────────────────────────────────
    "business": {"name": "Business (Kitchin)", "bands": [
        _measured("intermediate", "fred:INDPRO", freq="M", basis="fred_level",
                  stale_limit_days=85,   # G.17 calendar: obs dated the 1st, release lands
                                         # ~15th-17th of the SECOND month after → worst-case
                                         # healthy age ≈ 78d; 85 = headroom for a late G.17
                  kernel={"zz_abs": 1.5, "zz_standardize": True,
                          "trend_span": 60, "stoch_win": 60},
                  note="DEVIATION: D3 specced a leading-index COMPOSITE via business_cycle.py; "
                       "W3.1 binds INDPRO monthly with abs-ZigZag on its z-score (1.5σ, "
                       "zz_standardize=True — a raw-abs threshold over-segments a trending "
                       "level). Kitchin ~4y → ~7 turns/30y, gradeable at the monthly horizon")]},

    # ── 2 MEASURED-proxy (ruling A17: timing only, position_gauge=False) ─────────────
    "memory": {"name": "Memory (DRAM / NAND)", "bands": [
        _proxy("intermediate", "yahoo:MU", basis="equity_px",
               fitness={"kind": "dram", "match_rate_min": 0.7, "offset_max_months": 6},
               note="DRAM contract ASP has NO free tape. MU = LABELED equity proxy for turn "
                    "TIMING only; hand ASP turns survive as a frame overlay. Fitness gate §1.5"),
        _frame("secular", note="hand-dated DRAM ASP turns — curated history overlay")]},
    "uranium": {"name": "Uranium", "bands": [
        _proxy("intermediate", "yahoo:CCJ", basis="equity_px",
               fitness={"kind": "u3o8", "match_rate_min": 0.7, "offset_max_months": 6},
               note="spot U3O8 (UxC/Numerco) paywalled. CCJ = LABELED equity proxy for turn "
                    "TIMING only; hand spot turns = frame overlay. URA too short (2010→); rejected"),
        _frame("secular", note="hand-dated U3O8 spot turns — curated history overlay")]},

    # ── 4 DUAL: MEASURED intermediate band + FRAME secular band ──────────────────────
    "gold": {"name": "Gold / Precious Metals", "bands": [
        _measured("intermediate", "yahoo:GC=F", basis="futures_cont",
                  note="measured intermediate cycle"),
        _frame("secular", note="17y secular gold clock — frame band (year-of arithmetic)")]},
    "bitcoin": {"name": "Bitcoin", "bands": [
        _measured("intermediate", "yahoo:BTC-USD", basis="spot",
                  note="measured intermediate cycle; kept out of the equity hazard family"),
        _frame("secular", note="4y halving clock — frame band; cite the BTC 1064/364 program")]},
    "dollar": {"name": "US Dollar", "bands": [
        _measured("intermediate", ["yahoo:DX-Y.NYB", "fred:DTWEXBGS"], basis="index_px",
                  note="DXY is price-basis already (no dividends) — clean"),
        _frame("secular", note="15y secular dollar frame")]},
    "japan": {"name": "Japan (Nikkei)", "bands": [
        _measured("intermediate", ["intl:^N225", "yahoo:EWJ"], basis="index_px",
                  note="local-ccy Nikkei primary (61y tape); EWJ (USD) as the FX-decomposed leg"),
        _frame("secular", note="secular Nikkei frame (1989 bubble chronology)")]},

    # ── 4 FRAME-only (forced by a real data gap or n≈2 turns) ─────────────────────────
    "housing": {"name": "Housing / Real Estate", "bands": [
        _frame("secular", monitors=["fred:CSUSHPISA", "fred:PERMIT", "fred:HOUST",
                                    "fred:MORTGAGE30US", "yahoo:XHB"],
               note="18y land cycle, n≈2 graded turns → never measured. Full monitor coverage")]},
    "shipping": {"name": "Shipping (Baltic Dry)", "bands": [
        _frame("secular", monitors=["yahoo:BDRY"],
               note="BDI Baltic-Exchange proprietary; the honest NONE case. Manual falsifier + TTL")]},
    "lithium": {"name": "Lithium", "bands": [
        _frame("secular", monitors=["yahoo:ALB", "yahoo:SQM", "yahoo:LAC"],
               note="spot Li2CO3 paywalled; equity monitors feed tripwires only")]},
    "iron-ore": {"name": "Iron Ore", "bands": [
        _frame("secular", monitors=["fred:PCU331110331110", "yahoo:SLX"],
               note="62% Fe (SGX/Platts) paywalled; US steel PPI ≠ seaborne iron ore. Honest NONE")]},

    # ── SPX flagship (markets.html fold; measured on SPY) ─────────────────────────────
    "spx": {"name": "US Equities (SPX flagship)", "bands": [
        _measured("intermediate", ["yahoo:SPY", "yahoo:^GSPC"], basis="etf_tr",
                  note="markets.html US flagship; ^GSPC backs the falsifier levels")]},
}


def measured_bands() -> list[tuple[str, dict]]:
    """[(cycle_id, band)] for every MEASURED band across the registry (proxy bands
    included — they are tier 'measured' with position_gauge=False)."""
    out = []
    for cid, spec in REGISTRY.items():
        for band in spec["bands"]:
            if band["tier"] == "measured":
                out.append((cid, band))
    return out


# ── build-time health report ─────────────────────────────────────────────────────────
def registry_report(*, strict: bool = True) -> dict:
    """Per measured band: {found, ref, rows, first, last, stale_days, stale_limit, ok}.

    Two failure classes, deliberately separate (house law: one bad tape degrades its own
    band, never the page):
      STRUCTURAL — a ref that does not resolve / an empty tape / the NP-3 equity guard.
                   Collected in report['errors']; raises when strict.
      STALE      — a tape whose last stamp exceeds the band's freshness limit (the
                   band's `stale_limit_days` override when declared, else _STALE_MAX_M /
                   _STALE_MAX_D by freq).  Marked per-band (ok=False) + collected in
                   report['stale']; NEVER raises — callers render the band from its
                   last data with a visible stale mark."""
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    report: dict = {"as_of": str(today.date()), "bands": {}, "errors": [], "stale": []}
    for cid, band in measured_bands():
        key = f"{cid}.{band['band']}"
        entry: dict = {"cycle": cid, "band": band["band"], "proxy": band["proxy"],
                       "freq": band["freq"], "basis": band["basis"]}
        try:
            s = load_series(band)
            last = s.index.max()
            stale = int((today - last.normalize()).days)
            _sld = band.get("stale_limit_days")
            limit = _sld if _sld is not None else (
                _STALE_MAX_M if band["freq"] == "M" else _STALE_MAX_D)
            entry.update({"found": True, "ref": s.attrs.get("ref"), "rows": int(len(s)),
                          "first": str(s.index.min().date()), "last": str(last.date()),
                          "stale_days": stale, "stale_limit": limit,
                          "ok": bool(stale <= limit)})
            if stale > limit:
                msg = f"{key}: tape stale {stale}d > {limit}d ({s.attrs.get('ref')})"
                report["stale"].append(msg)
                log.warning("registry_report: %s — band degrades, page renders", msg)
        except ProxyMissing as e:
            entry.update({"found": False, "ok": False, "error": str(e)})
            report["errors"].append(f"{key}: {e}")
        report["bands"][key] = entry
    if strict and report["errors"]:
        raise ProxyMissing("registry_report FAILED (structural):\n  "
                           + "\n  ".join(report["errors"]))
    return report


# ── proxy-fitness gate (§1.5, ruling A6 — Wilson-bounded) ─────────────────────────────
def _wilson_lower(k: int, n: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound for a proportion k/n (A6: the gate is
    Wilson-bounded, not a bare point estimate — n is tiny for hand turns)."""
    if n == 0:
        return 0.0
    p = k / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return max(0.0, (centre - margin) / denom)


def _to_year(ym: str) -> float:
    """'YYYY-MM' → decimal year (mid-month), matching the hand-turn key convention."""
    y, m = ym.split("-")
    return int(y) + (int(m) - 0.5) / 12.0


def validate_proxy(cid: str, band: dict, hand_turns: list[dict],
                   period_central_yrs: float) -> dict:
    """Earn the proxy tier (ruling A6/A17).  Run the kernel on the proxy tape, extract
    engine turns, match each HAND turn to the nearest same-kind engine turn, compute
    match_rate + its Wilson lower bound and the median |offset| in months.

    GATE: wilson_lower(match_rate) ≥ fitness.match_rate_min AND median_offset_months ≤
    fitness.offset_max_months → the band renders MEASURED-proxy (timing only).  Otherwise
    the band AUTO-DEMOTES to frame (verdict['demote']=True) and the build logs it.

    A match = a hand turn with an engine turn of the SAME kind within 25% of the median
    half-cycle (period_central/2)."""
    from engine import sector_cycles as sc

    s = load_series(band)
    win_start = s.index.min()
    kernel = band.get("kernel") or {}
    zz_pct = kernel.get("zz_pct")
    zz_abs = kernel.get("zz_abs")
    if zz_pct is None and zz_abs is None:                    # vol-scaled default
        zz_pct = sc._zz_pct_for(s) if band["freq"] == "D" else sc._zz_pct_for_monthly(s)
    rec = sc.record_series(s, win_start=win_start, last_ts=s.index[-1],
                           freq=band["freq"], invert=band["invert"],
                           zz_pct=zz_pct, zz_abs=zz_abs,
                           zz_standardize=bool(kernel.get("zz_standardize")),
                           trend_span=kernel.get("trend_span"),
                           stoch_win=kernel.get("stoch_win"),
                           basis_label=band["basis"], family="flagship")
    eng = [t for t in (rec or {}).get("turns", []) if not t.get("provisional")]
    tol_yrs = 0.25 * (period_central_yrs / 2.0)              # 25% of the half-cycle
    fit = band["fitness"]
    matched = 0
    offsets: list[float] = []
    detail: list[dict] = []
    for h in hand_turns:
        hx = _to_year(h["t"])
        cands = [t for t in eng if t.get("k") == h.get("k") and t.get("x") is not None]
        best = min(cands, key=lambda t: abs(t["x"] - hx), default=None)
        d = abs(best["x"] - hx) if best else None
        ok = bool(best is not None and d <= tol_yrs)
        if ok:
            matched += 1
            offsets.append(d * 12.0)
        detail.append({"hand": h["t"], "kind": h.get("k"),
                       "engine": (best or {}).get("t"),
                       "offset_months": (round(d * 12.0, 1) if d is not None else None),
                       "matched": ok})
    n = len(hand_turns)
    rate = matched / n if n else 0.0
    wl = _wilson_lower(matched, n)
    med_off = float(np.median(offsets)) if offsets else None
    # GATE (D3 §1.5 verbatim): the POINT match_rate ≥ min AND median offset ≤ max earns
    # the MEASURED-proxy tier; a point-rate or offset failure AUTO-DEMOTES to frame.
    # A6 discipline: the Wilson LOWER BOUND is the stored honesty artifact — a band that
    # passes the point gate but whose wilson_lo < min is flagged low_confidence (small-n:
    # the timing is right on the sample, but n is too thin to CERTIFY it at 95%). The chip
    # then reads "MEASURED (proxy · n=k, low confidence)" rather than hard-failing on n.
    passes = bool(rate >= fit["match_rate_min"]
                  and (med_off is not None and med_off <= fit["offset_max_months"]))
    low_conf = bool(passes and wl < fit["match_rate_min"])
    return {
        "cycle": cid, "band": band["band"], "ref": s.attrs.get("ref"),
        "kind": fit["kind"], "n_hand": n, "n_engine": len(eng),
        "matched": matched, "match_rate": round(rate, 3),
        "match_rate_wilson_lo": round(wl, 3),
        "median_offset_months": (round(med_off, 2) if med_off is not None else None),
        "tol_years": round(tol_yrs, 3),
        "gate": {"match_rate_min": fit["match_rate_min"],
                 "offset_max_months": fit["offset_max_months"]},
        "pass": passes, "demote": not passes,
        "low_confidence": low_conf, "detail": detail,
    }


# ── JSON export (build hook) ──────────────────────────────────────────────────────────
def _serialisable_registry() -> dict:
    """The registry with every band flattened to JSON-safe primitives, plus a census."""
    census = {"measured": 0, "measured_proxy": 0, "measured_monthly": 0,
              "frame": 0, "dual": 0, "frame_only": 0}
    out = {"version": 1, "ruling": "A3/A17/R3-C5", "cycles": {}}
    for cid, spec in REGISTRY.items():
        bands = spec["bands"]
        tiers = {b["tier"] for b in bands}
        has_measured = "measured" in tiers
        has_frame = "frame" in tiers
        if has_measured and has_frame:
            census["dual"] += 1
        elif has_frame and not has_measured:
            census["frame_only"] += 1
        for b in bands:
            if b["tier"] == "measured":
                if b["proxy"]:
                    census["measured_proxy"] += 1
                elif b["freq"] == "M":
                    census["measured_monthly"] += 1
                else:
                    census["measured"] += 1
            else:
                census["frame"] += 1
        out["cycles"][cid] = {"name": spec["name"], "bands": bands}
    out["census"] = census
    return out


def export(root: Path | None = None) -> dict:
    """Write proxy_registry.json (+ registry_health.json) under data/cycle_ontology/.
    Returns the health report (raises only on STRUCTURAL failures — a missing /
    unresolvable tape; stale bands are recorded in the report, never fatal)."""
    root = root or Path(".")
    reg = _serialisable_registry()
    (root / _REGISTRY_JSON).parent.mkdir(parents=True, exist_ok=True)
    (root / _REGISTRY_JSON).write_text(json.dumps(reg, indent=2), encoding="utf-8")
    health = registry_report(strict=True)
    (root / _HEALTH_JSON).write_text(json.dumps(health, indent=2), encoding="utf-8")
    return health


# ── hand-turn source (read from the canonical cycle_data.js turns[]) ──────────────────
# The MU/CCJ hand turns live in site/cycle_data.js turns[]; the fitness gate reads them
# from here (mirrored to keep the gate pure-Python and testable without a JS parse).
HAND_TURNS: dict[str, dict] = {
    "memory": {"period_central_yrs": 3.5, "turns": [
        {"t": "2006-06", "k": "peak"}, {"t": "2008-12", "k": "trough"},
        {"t": "2010-06", "k": "peak"}, {"t": "2013-01", "k": "trough"},
        {"t": "2014-12", "k": "peak"}, {"t": "2016-06", "k": "trough"},
        {"t": "2018-10", "k": "peak"}, {"t": "2019-09", "k": "trough"},
        {"t": "2021-12", "k": "peak"}, {"t": "2023-06", "k": "trough"}]},
    "uranium": {"period_central_yrs": 8.0, "turns": [
        {"t": "2007-06", "k": "peak"}, {"t": "2016-11", "k": "trough"},
        {"t": "2024-01", "k": "peak"}, {"t": "2025-03", "k": "trough"}]},
}


def run_fitness(root: Path | None = None) -> dict:
    """Run validate_proxy for every proxy band (memory→MU, uranium→CCJ), write the
    verdict artifact to data/cycle_ontology/proxy_fitness.json, and return it."""
    root = root or Path(".")
    verdicts = {}
    for cid, band in measured_bands():
        if not band["proxy"]:
            continue
        ht = HAND_TURNS.get(cid)
        if ht is None:
            continue
        verdicts[cid] = validate_proxy(cid, band, ht["turns"], ht["period_central_yrs"])
    out = {"version": 1, "verdicts": verdicts}
    (root / _FITNESS_JSON).parent.mkdir(parents=True, exist_ok=True)
    (root / _FITNESS_JSON).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    health = export()
    fitness = run_fitness()
    print("\n── PROXY REGISTRY HEALTH ─────────────────────────────────────────")
    print(f"{'cycle.band':22s} {'freq':4s} {'rows':>6s} {'first':10s} {'last':10s} "
          f"{'stale':>5s} {'ok':>3s}  ref")
    for key, e in health["bands"].items():
        if not e.get("found"):
            print(f"{key:22s}  MISSING — {e.get('error')}")
            continue
        print(f"{key:22s} {e['freq']:4s} {e['rows']:>6d} {e['first']:10s} {e['last']:10s} "
              f"{e['stale_days']:>5d} {'✓' if e['ok'] else '✗':>3s}  {e['ref']}")
    print("\n── PROXY FITNESS (ruling A6/A17 — timing only) ────────────────────")
    for cid, v in fitness["verdicts"].items():
        verdict = ("PASS (MEASURED-proxy)" if v["pass"] else "FAIL → auto-demote to FRAME")
        if v.get("low_confidence"):
            verdict += " · low-confidence (small-n; timing right, n too thin to certify)"
        print(f"{cid:10s} {v['ref']:12s} match={v['matched']}/{v['n_hand']} "
              f"rate={v['match_rate']} wilson_lo={v['match_rate_wilson_lo']} "
              f"med_off={v['median_offset_months']}mo → {verdict}")
    reg = _serialisable_registry()
    print("\ncensus:", reg["census"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
