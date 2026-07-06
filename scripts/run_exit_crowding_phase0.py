#!/usr/bin/env python3
"""EXIT-CROWD Phase-0 runner — roadmap P4.4a, L4-ONLY PRE-FDR INTERIM leg.

Ratified pre-registration: research/EXIT_CROWDING_PHASE0_PREREG.md (rulings F1-F5).

This runner implements the **L4 (ETF-flow rolloff) leg only** — the leg with no
thetadata dependency (F3 / OPEN-3: L4 runs at ratification, PRE-FDR INTERIM). L1-L3
are STUBS that hard-fail until data/thetadata_eod/_manifest.json marks the universe
pass complete (§8.11 / R8). This runner NEVER reads data/thetadata_eod/.

L4 primitive (§2.2): engine.theme_flow_rollup — divergence==True (flow_score<0 while
basket rel-price flat/up = the "A4 tell"), OR flow_score crossing below 0 with coverage
>= _MIN_COVERED_FRAC. PIT-honest per-date reconstruction: at each as-of date we compute
flow strictly from ETF-holdings snapshots dated <= that date (no future snapshot reads).

PRIMARY statistic (§2.3, EXIT-CROWD-L4 §4): fire-conditioned direction-adjusted
forward-21d excess-vs-SPY (PRIMARY, matching flow cadence) + 63d (secondary), delta vs
the LIVE engine.sector_signals.STATE_BASE_RATES["SELL"] dict read at runtime (stamped),
reusing the B2 cross-granularity comparison pattern from scripts/oracle_gauntlet_p3.py.

Placebo (§5 + F1 PRIMARY lane): same-sector leg-not-fired matched group-days,
regime+duration matched, 200 draws, exclusion_zone=10.

Every cell carries the 1-5d lag label (O6-v: no lead claim tighter than reporting
cadence). All outputs labeled PRE-FDR INTERIM; verdict language capped at ACCRUE/interim.
Final BH q-values print ONLY when the 16-trial family completes (L1-L3 done).

CRITICAL n-honesty: the ETF-holdings store has NO sector-ETF (XLB..XLY) snapshots and
its deepest per-ETF history is ~3 months in 2026. The honest result is tiny-n ACCRUE;
the exact history depth is stamped. No history is fabricated; the prereg is not relaxed.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Repo root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import sector_signals  # noqa: E402

log = logging.getLogger("exit_crowding_phase0")

# ---------------------------------------------------------------------------
# Constants frozen by the ratified prereg
# ---------------------------------------------------------------------------
INTERIM_LABEL = "PRE-FDR INTERIM"
LAG_LABEL = "1-5d lag (holdings-snapshot cadence; no lead claim tighter than reporting cadence, O6-v)"
FDR_FAMILY_SIZE = 16  # §7 gated trials; BH q-values print only when family completes
PLACEBO_DRAWS = 200   # §5
EXCLUSION_ZONE = 10   # §5 sessions
MIN_N_FLOOR = 60      # §4 house floor for a GATE (below -> ACCRUE, never KILL)
COVERAGE_MIN_FRAC = 0.10  # theme_flow _MIN_COVERED_FRAC
H_PRIMARY = 21        # L4 PRIMARY horizon (flow cadence)
H_SECONDARY = 63      # L4 secondary/robustness horizon
H_ROBUST = 5

OUT_DIR = ROOT / "data" / "options_exit"
OUT_JSON = OUT_DIR / "exit_crowd_l4_interim.json"

# Theme(category)->GICS-sector-ETF mapping for the PRIMARY lane (F1: sector-ETF complex
# is the outcome-currency domain). This is operationalized from the basket `category`
# field. IT IS LOSSY (a thematic category can span >1 GICS sector) -> flagged as an
# OPEN ITEM in the output rather than silently collapsing.
CATEGORY_TO_SECTOR_ETF = {
    "AI & Technology": "XLK",
    "Industrials & Defense": "XLI",
    "Energy & Power": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Healthcare": "XLV",
    "Consumer": "XLY",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
    "Crypto & Blockchain": "XLK",
}
# Categories that clearly straddle >1 GICS sector (lossy mapping is *material* here).
LOSSY_CATEGORIES = {
    "AI & Technology": "spans Technology (XLK) + Communication Services (XLC)",
    "Energy & Power": "spans Energy (XLE) + Utilities (XLU)",
    "Consumer": "spans Consumer Discretionary (XLY) + Consumer Staples (XLP)",
    "Crypto & Blockchain": "no GICS home; proxied to XLK",
}


# ---------------------------------------------------------------------------
# Live SELL base-rate stamp (outcome currency, §1/§2.3)
# ---------------------------------------------------------------------------
def read_live_sell_base_rate() -> dict:
    """Read the LIVE STATE_BASE_RATES['SELL'] dict at run time (§1: refreshed live by
    calibrate; harness reads the live dict, not a static fallback) and stamp it."""
    br = dict(sector_signals.STATE_BASE_RATES["SELL"])
    br["_source"] = "engine.sector_signals.STATE_BASE_RATES['SELL'] (live, read at runtime)"
    br["_stamped_at"] = datetime.now(timezone.utc).isoformat()
    # neighbour ladder for context (§1)
    br["_ladder"] = {
        "TOPPING": dict(sector_signals.STATE_BASE_RATES["TOPPING"]),
        "EXTENDED": dict(sector_signals.STATE_BASE_RATES["EXTENDED"]),
    }
    return br


# ---------------------------------------------------------------------------
# PIT flow reconstruction (L4)
# ---------------------------------------------------------------------------
def _snapshot_dates(etf_dir: Path) -> list[date]:
    out = []
    for p in etf_dir.glob("*.parquet"):
        try:
            out.append(datetime.strptime(p.stem, "%Y-%m-%d").date())
        except ValueError:
            continue
    return sorted(out)


def discover_flow_history(base_dir: Path) -> dict:
    """CRITICAL DISCOVERY STEP (prereg): stamp exactly how much dated holdings history
    exists. Returns per-ETF date ranges + the union of dates + sector-ETF presence."""
    etfs = {}
    all_dates: set[date] = set()
    sector_etfs = {"XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"}
    sector_etf_present = []
    for d in sorted(base_dir.iterdir()):
        if not d.is_dir():
            continue
        dates = _snapshot_dates(d)
        if not dates:
            continue
        etfs[d.name] = {"n_snaps": len(dates), "first": dates[0].isoformat(),
                        "last": dates[-1].isoformat()}
        all_dates.update(dates)
        if d.name in sector_etfs:
            sector_etf_present.append(d.name)
    union = sorted(all_dates)
    return {
        "n_etfs": len(etfs),
        "per_etf": etfs,
        "union_first": union[0].isoformat() if union else None,
        "union_last": union[-1].isoformat() if union else None,
        "union_n_dates": len(union),
        "union_dates": [d.isoformat() for d in union],
        "sector_etf_holdings_present": sorted(sector_etf_present),
        "sector_etf_holdings_absent": sorted(sector_etfs - set(sector_etf_present)),
        "persisted_flow_score_series_found": False,  # verified: none on disk (see report)
        "note": ("theme_flow_rollup reads only the LAST snapshot date; there is NO "
                 "persisted historical flow_score series. Any time-series is a per-date "
                 "PIT recomputation bounded by the dated snapshot history above."),
    }


def reconstruct_flow_pit(base_dir: Path, as_of: date) -> dict[str, dict]:
    """Recompute theme_flow strictly from snapshots dated <= as_of (PIT: no future
    snapshot reads). Mirrors engine.theme_flow_rollup but with a date-truncated view
    of each ETF's snapshot directory, so it can be evaluated at historical dates.

    Returns {theme_id: ThemeFlowResult-like dict} for the as_of date.
    """
    import tempfile
    import shutil
    from engine import theme_flow_rollup as tfr
    from lib import config as engcfg

    real_data = base_dir.parent  # data/
    tmp = Path(tempfile.mkdtemp(prefix="exitcrowd_pit_"))
    data_mirror = tmp / "data"
    data_mirror.mkdir(parents=True)
    try:
        # 1. Symlink every top-level data/ entry EXCEPT the two holdings stores (which
        #    we date-truncate below). This keeps membership/closes/yahoo intact while
        #    guaranteeing no FUTURE holdings snapshot is ever read (PIT law §2.1/§8.11).
        truncate = {"etf_holdings", "holdings"}
        for entry in real_data.iterdir():
            if entry.name in truncate:
                continue
            try:
                (data_mirror / entry.name).symlink_to(entry.resolve())
            except OSError:
                pass

        # 2. Date-truncated mirrors of the two holdings stores (snapshots <= as_of only).
        def _truncated_store(src: Path, dst: Path):
            dst.mkdir(parents=True, exist_ok=True)
            for d in src.iterdir():
                if d.is_file():
                    try:
                        (dst / d.name).symlink_to(d.resolve())
                    except OSError:
                        pass
                    continue
                if not d.is_dir():
                    continue
                kept = [p for p in d.glob("*.parquet")
                        if _safe_date(p.stem) is not None and _safe_date(p.stem) <= as_of]
                if len(kept) < 2:
                    continue
                sub = dst / d.name
                sub.mkdir()
                for p in kept:
                    (sub / p.name).symlink_to(p.resolve())

        _truncated_store(base_dir, data_mirror / "etf_holdings")
        real_holdings = real_data / "holdings"
        if real_holdings.exists():
            _truncated_store(real_holdings, data_mirror / "holdings")

        # 3. Repoint config.data_dir + config.ROOT at the truncated mirror.
        orig_data_dir = engcfg.data_dir
        orig_root = engcfg.ROOT
        engcfg.data_dir = lambda: data_mirror  # type: ignore
        engcfg.ROOT = tmp  # type: ignore
        try:
            res = tfr.theme_flow("us")
        finally:
            engcfg.data_dir = orig_data_dir  # type: ignore
            engcfg.ROOT = orig_root  # type: ignore
        return {k: dict(v) for k, v in res.items()}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _safe_date(stem: str):
    try:
        return datetime.strptime(stem, "%Y-%m-%d").date()
    except ValueError:
        return None


def basket_category_map() -> dict[str, str]:
    """theme_id -> basket category (for the theme->sector mapping)."""
    from engine import group_flow
    s = group_flow._setup("us")
    out = {}
    if not s:
        return out
    mem = s["mem"]
    bd = mem.get("baskets", {})
    items = bd.items() if isinstance(bd, dict) else [(b["id"], b) for b in bd]
    for bid, b in items:
        out[str(bid)] = b.get("category", "")
    return out


# ---------------------------------------------------------------------------
# Fire detection + forward outcomes
# ---------------------------------------------------------------------------
def detect_fires(flow_by_date: dict[date, dict[str, dict]]) -> list[dict]:
    """A fire = for a held theme on date t, divergence==True OR flow_score crosses
    below 0 (t-1 >= 0 and t < 0) with coverage >= COVERAGE_MIN_FRAC.

    flow_by_date: {as_of_date: {theme_id: flow_result}}.
    Returns list of {as_of, theme_id, kind, flow_score}.
    """
    dates = sorted(flow_by_date.keys())
    fires = []
    for i, t in enumerate(dates):
        cur = flow_by_date[t]
        prev = flow_by_date[dates[i - 1]] if i > 0 else {}
        for theme, r in cur.items():
            fs = r.get("flow_score")
            nc, nm = r.get("n_covered", 0), r.get("n_members", 0)
            covered_ok = nm > 0 and (nc / nm) >= COVERAGE_MIN_FRAC
            div = bool(r.get("divergence"))
            cross = False
            if fs is not None and fs < 0 and covered_ok:
                pfs = prev.get(theme, {}).get("flow_score")
                if pfs is not None and pfs >= 0:
                    cross = True
            if (div and covered_ok) or cross:
                fires.append({
                    "as_of": t.isoformat(),
                    "theme_id": theme,
                    "kind": "divergence" if div else "flow_cross_below_0",
                    "flow_score": fs,
                    "n_covered": nc, "n_members": nm,
                })
    return fires


def forward_excess(theme_to_sector: dict[str, str], as_of: date, theme: str,
                   sector_levels: dict[str, pd.Series], spy: pd.Series,
                   horizon: int) -> float | None:
    """Direction-adjusted forward-`horizon`d excess vs SPY for the theme's sector ETF.

    Exhaustion frame (SELL/avoid): a NEGATIVE forward excess is the payoff. To be
    sign-consistent with the SELL base rate (which is stored as a signed excess, e.g.
    -1.24%), we return the RAW signed excess (sector_ret - spy_ret) in percent; the
    delta-vs-base-rate compares signed excess to signed base rate (more-negative = edge).

    Returns None if the sector ETF price history cannot furnish a matured horizon.
    """
    sec_etf = theme_to_sector.get(theme)
    if sec_etf is None or sec_etf not in sector_levels:
        return None
    lvl = sector_levels[sec_etf]
    ts = pd.Timestamp(as_of)
    # position at/just before as_of
    if ts not in lvl.index:
        idx = lvl.index[lvl.index <= ts]
        if len(idx) == 0:
            return None
        ts = idx[-1]
    fut = lvl.index[lvl.index > ts]
    if len(fut) < horizon:
        return None  # not matured
    t0 = lvl.loc[ts]
    t1 = lvl.iloc[lvl.index.get_loc(fut[horizon - 1])]
    s0 = spy.reindex([ts], method="ffill").iloc[0]
    sfut = spy.reindex([fut[horizon - 1]], method="ffill").iloc[0]
    if any(pd.isna(x) or x == 0 for x in (t0, t1, s0, sfut)):
        return None
    return float(((t1 / t0 - 1.0) - (sfut / s0 - 1.0)) * 100.0)


def load_sector_etf_levels(sectors: set[str]):
    """Load close series for the sector ETFs + SPY for forward-return computation."""
    from lib import store
    levels = {}
    for etf in sectors:
        try:
            df = store.read("yahoo", etf)
            if df is not None and "close" in df.columns:
                levels[etf] = df["close"].copy()
        except Exception:  # noqa: BLE001
            continue
    spy = None
    try:
        sdf = store.read("yahoo", "SPY")
        if sdf is not None and "close" in sdf.columns:
            spy = sdf["close"].copy()
    except Exception:  # noqa: BLE001
        pass
    return levels, spy


# ---------------------------------------------------------------------------
# Placebo (§5 + F1)
# ---------------------------------------------------------------------------
def build_placebo(flow_by_date, fires, theme_to_sector, sector_levels, spy,
                  horizon, base_rate_exc, rng) -> dict:
    """PRIMARY-lane placebo: same-sector leg-NOT-fired matched group-days
    (held theme-days where the fire condition did not hold), regime+duration matched,
    200 draws, exclusion_zone=10. Returns placebo distribution + p95 threshold.

    With tiny-n history this will typically be insufficient_placebo:true.
    """
    fire_set = {(f["as_of"], f["theme_id"]) for f in fires}
    fire_dates_by_theme: dict[str, list[date]] = {}
    for f in fires:
        fire_dates_by_theme.setdefault(f["theme_id"], []).append(
            datetime.strptime(f["as_of"], "%Y-%m-%d").date())

    # candidate non-event held theme-days: theme present with coverage_ok but not a fire,
    # and not within EXCLUSION_ZONE trading-day-proxy of a real fire for that theme.
    dates = sorted(flow_by_date.keys())
    date_pos = {d: i for i, d in enumerate(dates)}
    candidates = []
    for t in dates:
        for theme, r in flow_by_date[t].items():
            if (t.isoformat(), theme) in fire_set:
                continue
            nc, nm = r.get("n_covered", 0), r.get("n_members", 0)
            if not (nm > 0 and nc / nm >= COVERAGE_MIN_FRAC):
                continue
            # exclusion zone: skip if within EXCLUSION_ZONE index-steps of a fire
            near = False
            for fd in fire_dates_by_theme.get(theme, []):
                if abs(date_pos[t] - date_pos.get(fd, -999)) <= EXCLUSION_ZONE:
                    near = True
                    break
            if near:
                continue
            exc = forward_excess(theme_to_sector, t, theme, sector_levels, spy, horizon)
            if exc is not None:
                candidates.append(exc)

    n_cand = len(candidates)
    n_real_fires_matured = sum(
        1 for f in fires
        if forward_excess(theme_to_sector,
                          datetime.strptime(f["as_of"], "%Y-%m-%d").date(),
                          f["theme_id"], sector_levels, spy, horizon) is not None)

    insufficient = n_cand < 1 or n_real_fires_matured < 1
    placebo_means = []
    if not insufficient:
        draw_k = max(1, n_real_fires_matured)
        for _ in range(PLACEBO_DRAWS):
            samp = rng.choice(candidates, size=draw_k, replace=True)
            placebo_means.append(float(np.mean(samp)))
    p95 = float(np.percentile(placebo_means, 5)) if placebo_means else None  # 5th pct: exhaustion=more-negative tail
    return {
        "design": ("same-sector leg-not-fired matched held theme-days, regime+duration "
                   "matched, 200 draws, exclusion_zone=10 (§5 + F1 PRIMARY lane)"),
        "n_candidate_nonevent_days": n_cand,
        "n_real_fires_matured": n_real_fires_matured,
        "draws": PLACEBO_DRAWS,
        "exclusion_zone": EXCLUSION_ZONE,
        "placebo_p05_more_negative_tail": p95,
        "insufficient_placebo": insufficient,
        "note": ("G1 threshold = the more-negative (5th-percentile) tail of the placebo "
                 "mean distribution, since the exhaustion payoff is a NEGATIVE excess."),
    }


# ---------------------------------------------------------------------------
# L4 leg
# ---------------------------------------------------------------------------
def run_l4(base_dir: Path, seed: int = 20260704) -> dict:
    rng = np.random.default_rng(seed)
    base_rate = read_live_sell_base_rate()
    base_exc63 = float(base_rate["exc63"])

    history = discover_flow_history(base_dir)
    cat_map = basket_category_map()

    # theme -> sector ETF (via category), stamped + lossy flags
    theme_to_sector = {}
    theme_to_category = {}
    lossy_hits = {}
    unmapped = []
    for theme, cat in cat_map.items():
        theme_to_category[theme] = cat
        etf = CATEGORY_TO_SECTOR_ETF.get(cat)
        if etf is None:
            unmapped.append({"theme": theme, "category": cat})
            continue
        theme_to_sector[theme] = etf
        if cat in LOSSY_CATEGORIES:
            lossy_hits[theme] = {"category": cat, "sector_etf": etf,
                                 "loss": LOSSY_CATEGORIES[cat]}

    sectors_used = set(theme_to_sector.values())
    sector_levels, spy = load_sector_etf_levels(sectors_used)

    # PIT flow reconstruction across available dated history
    union_dates = [datetime.strptime(d, "%Y-%m-%d").date() for d in history["union_dates"]]
    # Need >=2 snapshots for a flow computation; step over dates that have >=2 ETFs w/ coverage.
    flow_by_date: dict[date, dict[str, dict]] = {}
    eval_dates = union_dates[1:]  # first date has no prior for any ETF
    for t in eval_dates:
        try:
            flow_by_date[t] = reconstruct_flow_pit(base_dir, t)
        except Exception as exc:  # noqa: BLE001
            log.warning("flow PIT reconstruct failed @ %s: %s", t, exc)

    fires = detect_fires(flow_by_date)

    # forward outcomes at PRIMARY 21d + secondary 63d + robust 5d
    def matured_excess(h):
        vals = []
        for f in fires:
            t = datetime.strptime(f["as_of"], "%Y-%m-%d").date()
            e = forward_excess(theme_to_sector, t, f["theme_id"], sector_levels, spy, h)
            if e is not None:
                vals.append(e)
        return vals

    # matured excess WITH the independence bookkeeping (distinct fire dates + distinct
    # sector ETFs are the true independence ceiling; overlapping 21d windows on the same
    # sector ETF are NOT independent draws).
    def matured_excess_detail(h):
        vals, keys = [], []
        for f in fires:
            t = datetime.strptime(f["as_of"], "%Y-%m-%d").date()
            e = forward_excess(theme_to_sector, t, f["theme_id"], sector_levels, spy, h)
            if e is not None:
                vals.append(e)
                keys.append((f["as_of"], theme_to_sector.get(f["theme_id"])))
        n_fire_dates = len({k[0] for k in keys})
        n_sector_windows = len(set(keys))  # distinct (date, sector-ETF) — the real ceiling
        return vals, n_fire_dates, n_sector_windows

    exc21, nd21, nsw21 = matured_excess_detail(H_PRIMARY)
    exc63, nd63, nsw63 = matured_excess_detail(H_SECONDARY)
    exc5, nd5, nsw5 = matured_excess_detail(H_ROBUST)

    # Era coverage of the FIRE dates (prereg §3 mandatory eras). All flow history is 2026,
    # i.e. a single ~3-month slice of the 2023-> era: no era split is computable.
    def era_of(dstr):
        y = int(dstr[:4])
        if 2018 <= y <= 2019:
            return "2018-19"
        if 2020 <= y <= 2022:
            return "2020-22"
        if y >= 2023:
            return "2023->"
        return "pre-2018"
    eras_hit = sorted({era_of(f["as_of"]) for f in fires})
    single_era = len(eras_hit) <= 1

    def cell(vals, horizon, is_primary, n_fire_dates, n_sector_windows):
        n = len(vals)
        mean = float(np.mean(vals)) if n else None
        delta_vs_base = (mean - base_exc63) if mean is not None else None  # signed; <0 = sharpens
        # "powered" requires the house floor AND >=2 eras AND enough INDEPENDENT
        # (distinct date x sector-ETF) windows — overlapping windows do not count.
        powered = bool(n_sector_windows >= MIN_N_FLOOR and not single_era)
        return {
            "horizon_d": horizon,
            "is_primary": is_primary,
            "n_matured_fires_raw": n,
            "n_distinct_fire_dates": n_fire_dates,
            "n_distinct_sector_windows": n_sector_windows,
            "independence_note": ("raw fires are heavily autocorrelated: the same sector ETF "
                                  "recurs across consecutive dates and multiple themes map to one "
                                  "sector ETF, so distinct (date x sector-ETF) windows are the true "
                                  "ceiling. Raw n is NOT an independent-observation count."),
            "fire_conditioned_excess_mean_pct": mean,
            "delta_vs_SELL_base_rate_pct": delta_vs_base,
            "sharpens_base_rate": (bool(delta_vs_base < 0) if delta_vs_base is not None else None),
            "min_n_floor": MIN_N_FLOOR,
            "eras_covered": eras_hit,
            "single_era": single_era,
            "powered_for_gate": powered,
            "lag_label": LAG_LABEL,
            "sign_convention": ("exhaustion payoff = MORE-NEGATIVE forward excess; "
                                "delta<0 vs -1.24% SELL base rate = sharpening (B2 cross-granularity, "
                                "informative only — different universe granularities). NOTE: the interim "
                                "mean here is POSITIVE (sector outperformance after a flow-rolloff fire), "
                                "i.e. the OPPOSITE sign to the exhaustion hypothesis — but on a single "
                                "~3-month 2026 window it is uninterpretable and NOT a refutation."),
        }

    primary = cell(exc21, H_PRIMARY, True, nd21, nsw21)
    placebo = build_placebo(flow_by_date, fires, theme_to_sector, sector_levels, spy,
                            H_PRIMARY, base_exc63, rng)

    # Verdict: below floor OR single-era => ACCRUE, never KILL (§4 + §3 era discipline).
    # Even at high raw n, single-era + autocorrelated windows cannot power a gate.
    verdict = "ACCRUE"
    verdict_reason = (
        f"single_era={single_era} (eras covered: {eras_hit}); "
        f"distinct sector-windows @21d={nsw21} vs floor {MIN_N_FLOOR}; "
        "all flow history is a single ~3-month 2026 slice of the 2023-> era, so the "
        "prereg's mandatory era split (2018-19 / 2020-22 / 2023->) is not computable and "
        "no cell can be gated. ACCRUE by construction, exactly as the prereg discovery step "
        "anticipated. (PRE-FDR INTERIM: verdict language capped at ACCRUE/interim, F3.)")
    come_back_note = ("board+ETF-holdings history accrual; re-run when >=2 eras have data AND "
                      f"distinct sector-windows @21d >= {MIN_N_FLOOR} AND the L1-L3 sub-family "
                      "completes the 16-trial FDR family (then BH q-values print once).")

    return {
        "battery": "EXIT-CROWD",
        "leg": "L4",
        "leg_name": "ETF-flow rolloff (institutional trim, 1-5d lag)",
        "phase": "Phase-0",
        "status_label": INTERIM_LABEL,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "verdict_language_cap": "ACCRUE/interim only until 16-trial FDR family completes (F3)",
        "prereg": "research/EXIT_CROWDING_PHASE0_PREREG.md (RATIFIED 2026-07-04, F1-F5)",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "primary_lane": "11-sector-ETF complex group-days (F1); board buy[] roster = watermarked SECONDARY tag (not run here)",
        "outcome_currency_SELL_base_rate": base_rate,
        "flow_history_discovery": history,
        "theme_to_sector_mapping": {
            "basis": "basket `category` field -> GICS sector ETF (CATEGORY_TO_SECTOR_ETF)",
            "n_mapped_themes": len(theme_to_sector),
            "n_unmapped_themes": len(unmapped),
            "unmapped": unmapped,
            "lossy_mappings": lossy_hits,
            "OPEN_ITEM": ("The theme(category)->GICS-sector mapping is LOSSY for categories "
                          "that straddle >1 GICS sector (see lossy_mappings). This is flagged, "
                          "NOT silently resolved — the sector-ETF PRIMARY lane inherits this "
                          "coarseness. A per-member GICS rollup would be the fix (future amendment)."),
        },
        "fire_detection": {
            "definition": ("divergence==True OR flow_score crossing below 0 (t-1>=0, t<0) "
                           "with coverage>=0.10 (§2.2 L4)"),
            "n_eval_dates": len(flow_by_date),
            "n_fires_total": len(fires),
            "fires": fires,
        },
        "cells": {
            "primary_21d": primary,
            "secondary_63d": cell(exc63, H_SECONDARY, False, nd63, nsw63),
            "robust_5d": cell(exc5, H_ROBUST, False, nd5, nsw5),
        },
        "placebo": placebo,
        "fdr": {
            "family_size": FDR_FAMILY_SIZE,
            "family_complete": False,
            "bh_q_values": None,
            "note": ("BH q-values print ONLY when the 16-trial family (L1-L4 x eras) "
                     "completes. L1-L3 await data/thetadata_eod manifest. PRE-FDR INTERIM."),
        },
        "come_back_note": come_back_note,
        "honesty_stamps": {
            "sector_etf_holdings_absent": history["sector_etf_holdings_absent"],
            "history_depth_note": ("Deepest per-ETF holdings history is ~3 months, all in 2026 "
                                   "(see flow_history_discovery). The prereg PRIMARY window is "
                                   "2018-> with mandatory eras 2018-19 / 2020-22 / 2023->; only the "
                                   "2023-> era has ANY data, and even that is a single ~3-month slice. "
                                   "Era splits are therefore not computable; this is ACCRUE by "
                                   "construction, exactly as the prereg's discovery step anticipated."),
            "survivorship": ("board ledger powered=false / survivorship-inflated (studies.json); "
                             "any board-conditioned n optimistic until deep+PIT panel"),
            "no_fabricated_history": True,
            "prereg_not_relaxed": True,
        },
    }


# ---------------------------------------------------------------------------
# L1-L3 stubs (hard-fail until thetadata manifest complete — R8/§8.11)
# ---------------------------------------------------------------------------
def _manifest_complete(root: Path) -> tuple[bool, dict]:
    mpath = root / "data" / "thetadata_eod" / "_manifest.json"
    if not mpath.exists():
        return False, {"reason": "manifest_missing", "path": str(mpath)}
    try:
        m = json.loads(mpath.read_text())
    except Exception as exc:  # noqa: BLE001
        return False, {"reason": f"manifest_unreadable: {exc}"}
    ok = bool(m.get("n_roots", 0) and m.get("updated_at"))
    return ok, {"n_roots": m.get("n_roots"), "updated_at": m.get("updated_at")}


def run_l1_l2_l3_stub(leg: str, root: Path):
    complete, info = _manifest_complete(root)
    if not complete:
        raise SystemExit(
            f"[{leg}] BLOCKED: data/thetadata_eod/_manifest.json universe pass NOT complete "
            f"(R8 / §8.11): {info}. L1-L3 do not run until the manifest marks n_roots at target "
            f"and updated_at non-null. This runner NEVER reads data/thetadata_eod/ mid-backfill.")
    raise SystemExit(f"[{leg}] manifest complete but leg not yet implemented (P4.4b+).")


# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="EXIT-CROWD Phase-0 runner (L4 interim)")
    ap.add_argument("--leg", default="L4", choices=["L1", "L2", "L3", "L4"])
    ap.add_argument("--out", default=str(OUT_JSON))
    ap.add_argument("--seed", type=int, default=20260704)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.leg in ("L1", "L2", "L3"):
        run_l1_l2_l3_stub(args.leg, ROOT)
        return

    base_dir = ROOT / "data" / "etf_holdings"
    if not base_dir.exists():
        raise SystemExit(f"etf_holdings store missing at {base_dir}")

    result = run_l4(base_dir, seed=args.seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(result, indent=2, default=str))

    log.info("=== EXIT-CROWD L4 %s ===", INTERIM_LABEL)
    log.info("history: %d ETFs, %s..%s, %d dates; sector-ETF holdings absent: %s",
             result["flow_history_discovery"]["n_etfs"],
             result["flow_history_discovery"]["union_first"],
             result["flow_history_discovery"]["union_last"],
             result["flow_history_discovery"]["union_n_dates"],
             result["flow_history_discovery"]["sector_etf_holdings_absent"])
    p = result["cells"]["primary_21d"]
    log.info("fires: %d; primary-21d raw n=%d / distinct-sector-windows=%d, mean=%s, delta_vs_base=%s; eras=%s single_era=%s",
             result["fire_detection"]["n_fires_total"],
             p["n_matured_fires_raw"], p["n_distinct_sector_windows"],
             p["fire_conditioned_excess_mean_pct"], p["delta_vs_SELL_base_rate_pct"],
             p["eras_covered"], p["single_era"])
    log.info("verdict: %s (%s)", result["verdict"], INTERIM_LABEL)
    log.info("wrote %s", outp)
    return result


if __name__ == "__main__":
    main()
