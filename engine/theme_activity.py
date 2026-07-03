"""Multi-source REAL-ACTIVITY observable — the v2 engine behind the Divergence Radar.

Fuses several INDEPENDENT non-price observables of "is real activity actually happening
on this theme" into one per-basket signal, laid against price (in engine/radar.py):

  * usaspending      — federal contract obligations  (collectors/usaspending.py)   [strong]
  * quiver_govcontract — Quiver new-award $          (collectors/quiver.py event tbl)[strong]
  * congress_netbuy  — congressional net-buy $         (Quiver event tbl, signed)   [medium]
  * lobbying_ramp    — lobbying spend ramp             (Quiver event tbl)           [medium]
  * news_velocity    — modeled macro-news flow         (engine/news_flow.py)        [weak/context]

TWO SOURCE KINDS, two metrics:
  * "wide"  (usaspending): a deep date-indexed [month x ticker] store series read YoY
    (recent 3 months vs the same 3 months a year ago) — kills federal seasonality.
  * "quiver": one of MAIN's append-only Quiver EVENT tables (collectors/quiver.py ->
    data/quiver/<dataset>.parquet, read via engine.altdata). These are forward-accumulating
    (no year of history yet), so the metric is recent-60d vs prior-60d, aggregated over the
    basket's members. Reuses altdata's _read/_usd/_side/_dt parsers — does NOT add a parallel
    collector.
Each source → a metric → a cross-sectional robust-z leg; legs are weight-fused into
`fused_obs_z` (the divergence/salience input) and `fused_accel` (the up/down direction).
Absent sources (no key, no table, thin coverage) are skipped and down-weighted to zero — the
radar degrades gracefully and sharpens as sources fill in. Raw ratios are winsorised
(ACCEL_CLAMP) against small-denominator blow-ups on thin windows.

CROWDING sources (off-exchange short ratio, WSB) are deliberately NOT fused here (the
asymmetry invariant: independent real-activity divergence UPGRADES ahead of price; crowding
only ever trims).

W0d extensions:
  * run-rate surprise (rr_surprise) — DOES alter fused_obs_z BY DESIGN: a 30% intra-leg blend
    inside the usaspending metric before the cross-sectional z (masterplan W0d; corr with the
    YoY metric 0.319 = additive), zeroed during US fiscal-year-end surge months (Sep/Oct) via
    the LAG-derived gate (R9b). The real invariant: this module's output stays on the
    context-only radar path (radar is_context_only) — nothing here reaches stock_score,
    spotlight, or regime.classify. The two extensions below ARE display-only and never
    enter fused_obs_z/fused_accel:
  * pipeline_to_award — count-based SAM→USAspending conversion context per basket; PIPELINE_LAG
    is a labeled assumption, not backtested. Display detail only, never enters fused_obs_z.
  * new_programs — first-ever NAICS/CFDA code appearance per basket, loaded from
    data/theme_activity/program_ledger.parquet (written by collectors at run time). Binary
    regime event, not a z-scored leg.

This module owns the shared primitives (robust_z + source_accel + the YoY constants);
engine/radar.py imports them. It does NOT import radar (no cycle). Display/context only.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# --- shared primitives (radar.py re-exports these) ---------------------------
LAG_MONTHS = 3            # most-recent award months are incomplete -> drop them
RECENT_MONTHS = 3        # "recent" window
YOY_LAG = 12             # compare recent window to the SAME months a year ago (kills seasonality)
MIN_COVERED = 2          # a basket needs >=2 covered members in a source to use that source
MIN_BASE_USD = 10e6      # ignore trivially small footprints (year-ago 3-month spend)
ACCEL_UP = 1.25          # recent / year-ago >= this -> accelerating
ACCEL_DOWN = 0.80        # <= this -> cooling
ACCEL_CLAMP = (0.05, 20.0)  # winsorise the raw ratio (small-denominator blow-ups on thin windows)
Z_CLAMP = 3.5            # winsorise robust-z (tight cross-section -> tiny MAD -> blow-ups)
NEWS_WEIGHT = 0.5        # the modeled-news leg carries a deliberately low fusion weight
QUIVER_RECENT_D = 60     # Quiver event tables are forward-accumulating -> recent vs prior window
QUIVER_PRIOR_D = 60      # (NOT YoY: those tables don't have a year of history yet)

# --- W0d: run-rate surprise constants ----------------------------------------
# Blend weight of rr_surprise_metric inside the usaspending leg metric (before cross-sectional z).
# Zeroed via _rr_sept_gate() during the US fiscal-year-end surge window (Sep/Oct).
# R9b: the gate derives from LAG_MONTHS — never hardcode calendar months.
RR_WEIGHT = 0.30          # 30% rr_surprise, 70% YoY; correlation with YoY leg = 0.319 (additive)
RUNRATE_TRAIL_M = 9       # trailing months for run-rate denominator (excludes recent window)
# Minimum history (after lag drop) needed to compute rr_surprise = RECENT_MONTHS + RUNRATE_TRAIL_M
_RR_MIN_HISTORY = RECENT_MONTHS + RUNRATE_TRAIL_M  # 12 months of usable data

# US fiscal-year-end surge months: Sep (9) + Oct (10). Awards flood in on Sep 30 deadline and
# get posted in Oct. rr_surprise fires a false positive every year in these months; gate it.
_SEPT_SURGE_MONTHS = frozenset({9, 10})

# --- W0d: pipeline-to-award constants ----------------------------------------
# Labeled assumption: SAM solicitation -> USAspending award lag by basket category.
# NOT backtested — 26 months of obligations history is insufficient to empirically validate.
# Display context only; never enters fused_obs_z.
PIPELINE_LAG_MONTHS: dict[str, int] = {
    "defense": 12, "space_economy": 12, "nuclear_power": 18,
    "ai_semiconductors": 9, "semicap_equipment": 9,
    "critical_minerals": 12, "power_grid": 9,
    "_default": 12,
}

# fusable spend/activity sources (crowding sources are handled separately, down-size only).
# Two kinds: "wide" = a date-indexed [month x ticker] store series read YoY (usaspending);
# "quiver" = one of main's append-only Quiver EVENT tables (collectors/quiver.py ->
# data/quiver/<dataset>.parquet), read via engine.altdata on a recent-vs-prior window and
# aggregated to the basket. label_* are the bilingual source-fusion-bar strings.
SOURCES: list[dict] = [
    {"name": "usaspending", "kind": "wide", "group": "usaspending", "series": "obligations",
     "weight": 1.0, "signed": False, "min_base": 10e6, "label_en": "Federal contracts", "label_zh": "联邦合同"},
    {"name": "usaspending_assistance", "kind": "wide", "group": "usaspending", "series": "grants_loans",
     "weight": 0.85, "signed": False, "min_base": 5e6, "recent_months": 6, "seasonal": False,
     "label_en": "Federal grants/loans", "label_zh": "联邦补助/贷款"},
    {"name": "quiver_govcontract", "kind": "quiver", "dataset": "govcontracts",
     "date": ["Date", "action_date"], "value": ["Amount"], "signed": False, "min_prior": 5e5,
     "weight": 1.0, "label_en": "Gov contracts (Quiver)", "label_zh": "政府合同"},
    {"name": "congress_netbuy", "kind": "quiver", "dataset": "congress",
     "date": ["TransactionDate", "ReportDate", "Date"], "value": ["Range", "Amount"], "signed": True,
     "txn_col": "Transaction", "min_prior": 0.0, "weight": 0.6, "label_en": "Congress net-buy", "label_zh": "国会净买入"},
    {"name": "lobbying_ramp", "kind": "quiver", "dataset": "lobbying",
     "date": ["Date"], "value": ["Amount"], "signed": False, "min_prior": 5e4,
     "weight": 0.7, "label_en": "Lobbying ramp", "label_zh": "游说支出"},
    {"name": "edgar_8k_velocity", "kind": "theme_event", "group": "edgar", "series": "material_8k_velocity",
     "min_prior": 1.0, "weight": 0.45, "label_en": "8-K material events", "label_zh": "重大事件公告"},
    # Grants.gov pre-award FOA flow (gated: needs GRANTS_GOV_API_KEY -> collector emits the
    # parquet; absent -> theme_event loader returns None and the source is silently skipped).
    {"name": "grants_foa", "kind": "theme_event", "group": "grants_gov", "series": "foa_velocity",
     "min_prior": 1.0, "weight": 0.45, "label_en": "Federal grant FOAs", "label_zh": "联邦资助公告"},
    # SAM.gov pre-award contract OPPORTUNITIES by NAICS (gated: needs SAM_API_KEY -> collector
    # emits the parquet; absent -> theme_event loader returns None and the source is skipped).
    {"name": "sam_presolicitation", "kind": "theme_event", "group": "sam_gov", "series": "opp_velocity",
     "min_prior": 1.0, "weight": 0.5, "label_en": "Pre-award solicitations", "label_zh": "招标预告"},
    # Federal Register policy-document velocity (keyless; collector runs nightly; absent -> silently skipped).
    # Two-stage AGENCY-SLUG x TERM filter maps 18 config themes to FR RULE/PRORULE/NOTICE/PRESDOCU counts.
    {"name": "fedreg_velocity", "kind": "theme_event", "group": "federal_register", "series": "reg_velocity",
     "min_prior": 1.0, "weight": 0.5, "label_en": "Regulatory pipeline", "label_zh": "监管动态"},
]


def robust_z(values: list[float]) -> list[float]:
    """Median/MAD z (robust to the small, lumpy cross-section), winsorised to +/-Z_CLAMP."""
    arr = np.asarray([v if v is not None and np.isfinite(v) else np.nan for v in values], float)
    good = arr[~np.isnan(arr)]
    if len(good) < 2:
        return [0.0] * len(values)
    med = float(np.median(good))
    mad = float(np.median(np.abs(good - med))) * 1.4826
    scale = mad if mad > 1e-9 else float(np.std(good))
    if not scale or scale < 1e-9:
        return [0.0] * len(values)
    return [0.0 if np.isnan(v) else float(np.clip((v - med) / scale, -Z_CLAMP, Z_CLAMP)) for v in arr]


def _rr_sept_gate(monthly: pd.Series) -> float:
    """Return the effective rr_surprise blend weight after the R9b September gate.

    The US fiscal year ends Sep 30; obligations flood in during Sep–Oct and cause a false
    rr_surprise spike every year.  Gate: zero RR_WEIGHT when the LAG-adjusted recent window
    (the last RECENT_MONTHS rows of `monthly`, which has already had LAG_MONTHS dropped)
    overlaps the surge months {9, 10}.

    Derivation is PURELY from the LAG_MONTHS constant — no hardcoded calendar month numbers
    appear here (R9b ruling).  The surge months set (_SEPT_SURGE_MONTHS) is defined once at
    module level as the policy constant."""
    if len(monthly) < RECENT_MONTHS:
        return 0.0
    recent_idx = monthly.index[-RECENT_MONTHS:]
    if any(ts.month in _SEPT_SURGE_MONTHS for ts in recent_idx):
        return 0.0
    return RR_WEIGHT


def source_accel(wide: pd.DataFrame, covered: list[str], *, signed: bool = False,
                 min_base: float = MIN_BASE_USD, recent_months: int = RECENT_MONTHS,
                 seasonal: bool = True) -> dict | None:
    """Self-referential change for one source over a basket's covered members.
    Unsigned (spend): accel = recent / prior, metric = log(accel).
    Signed (net flows that can be negative): metric = (recent - prior) / scale, accel = None.

    seasonal=True (federal CONTRACTS): prior = the SAME `recent_months` a year ago (kills the
    federal fiscal-year-end seasonality + award-posting lag). seasonal=False (lumpy/episodic
    GRANTS): prior = the immediately-preceding `recent_months` (sequential) — grants are
    one-off events with no clean YoY base, so a year-ago window is usually empty.

    W0d: for seasonal=True (usaspending obligations only), also computes rr_surprise — the
    ratio of the recent window to the trailing RUNRATE_TRAIL_M month average.  This is a
    step-change detector that is additive (corr with YoY=0.319) and blended at 30% inside
    the returned metric.  The blend weight is zeroed by _rr_sept_gate() during Sep/Oct per
    R9b.  rr_surprise and rr_surprise_metric are returned as extra keys for display."""
    cols = [c for c in covered if c in wide.columns]
    if len(cols) < MIN_COVERED:
        return None
    monthly = wide[cols].sum(axis=1, min_count=1).dropna().sort_index()
    if LAG_MONTHS:
        monthly = monthly.iloc[:-LAG_MONTHS] if len(monthly) > LAG_MONTHS else monthly.iloc[:0]
    need = recent_months + (YOY_LAG if seasonal else recent_months)
    if len(monthly) < need:
        return None
    recent = float(monthly.iloc[-recent_months:].sum())
    if seasonal:
        prior = float(monthly.iloc[-(recent_months + YOY_LAG):-YOY_LAG].sum())
    else:
        prior = float(monthly.iloc[-2 * recent_months:-recent_months].sum())
    if signed:
        scale = max(abs(prior), abs(recent), min_base, 1.0)
        metric = (recent - prior) / scale
        accel = None
    else:
        if prior < min_base or prior <= 0:
            return None
        accel = float(np.clip(recent / prior, *ACCEL_CLAMP))
        metric = float(np.log(accel))

    result: dict = {"accel": None if accel is None else round(accel, 3),
                    "recent_3m_usd": round(recent, 0), "base_3m_usd": round(prior, 0),
                    "metric": float(metric), "n_covered": len(cols), "covered": cols}

    # W0d: run-rate surprise — seasonal leg only, when sufficient trailing history exists.
    # Blend (with September gate) inside metric BEFORE returning; do not add a separate SOURCES leg.
    if seasonal and not signed and len(monthly) >= _RR_MIN_HISTORY:
        trail_window = monthly.iloc[-(recent_months + RUNRATE_TRAIL_M):-recent_months]
        trail_avg = float(trail_window.mean())  # per-month average over trailing 9 months
        if trail_avg > 0 and trail_avg * recent_months >= min_base:
            rr_raw = float(np.clip(recent / (trail_avg * recent_months), *ACCEL_CLAMP))
            rr_metric = float(np.log(rr_raw))
            rr_w = _rr_sept_gate(monthly)
            result["rr_surprise"] = round(rr_raw, 3)
            result["rr_surprise_metric"] = round(rr_metric, 4)
            result["rr_sept_gated"] = rr_w == 0.0
            if rr_w > 0.0:
                # Blend inside the metric before cross-sectional z (R9b: zero during surge months)
                result["metric"] = float((1.0 - rr_w) * metric + rr_w * rr_metric)

    return result


def _live_members(b: dict) -> list[str]:
    return [m.get("symbol") for m in b.get("members", []) if m.get("symbol")]


def _ok(df) -> pd.DataFrame | None:
    return df if df is not None and not df.empty else None


def _load_source(src: dict, sources_data: dict | None) -> pd.DataFrame | None:
    """Load a 'wide' source: a date-indexed [month x ticker] store series (usaspending).
    When sources_data is injected (test mode) it is authoritative — never fall through to disk."""
    if sources_data is not None:
        return _ok(sources_data.get(src["name"]))
    try:
        return _ok(store.read(src["group"], src["series"]))
    except Exception:  # noqa: BLE001
        return None


def _load_quiver(src: dict, sources_data: dict | None) -> pd.DataFrame | None:
    """Load a Quiver EVENT table (main's collectors/quiver.py). Injectable by dataset name;
    injection is authoritative (hermetic) — never read the real disk tables under injection."""
    if sources_data is not None:
        return _ok(sources_data.get(src["dataset"]))
    try:
        from engine import altdata
        return _ok(altdata._read(src["dataset"]))
    except Exception:  # noqa: BLE001
        return None


def _load_theme_event(src: dict, sources_data: dict | None) -> pd.DataFrame | None:
    """Load a 'theme_event' source: a small PRE-AGGREGATED per-basket frame the collector
    itself produced (basket_id -> recent_count / prior_count [+ optional covered/n_members]).
    Used for theme-level observables that have NO per-ticker breakdown — federal grant FOAs
    keyed by CFDA, SEC 8-K material-event counts per basket, etc. The collector did the
    member->basket roll-up, so the fuser just reads counts. Injectable (hermetic)."""
    df = sources_data.get(src["name"]) if sources_data is not None else None
    if df is None and sources_data is None:
        try:
            p = config.data_dir() / src["group"] / f"{src['series']}.parquet"
            df = pd.read_parquet(p) if p.exists() else None
        except Exception:  # noqa: BLE001
            return None
    if df is None or df.empty:
        return None
    if "basket_id" in df.columns:
        df = df.set_index("basket_id")
    return df


def _load_for(src: dict, sources_data: dict | None) -> pd.DataFrame | None:
    """Dispatch a source to its loader by `kind` ('wide' | 'quiver' | 'theme_event')."""
    kind = src.get("kind")
    if kind == "wide":
        return _load_source(src, sources_data)
    if kind == "quiver":
        return _load_quiver(src, sources_data)
    if kind == "theme_event":
        return _load_theme_event(src, sources_data)
    return None


def _quiver_basket_metric(src: dict, members: list[str], *, today=None,
                          event_df: pd.DataFrame | None = None) -> dict | None:
    """Per-basket recent-vs-prior activity from one Quiver event table. Filters the event
    stream to the basket's members, then compares the last QUIVER_RECENT_D days to the prior
    window. Unsigned (gov-contract / lobbying $): accel = recent/prior. Signed (congress
    net-buy: purchase +, sale −): metric = (recent − prior)/scale. Reuses engine.altdata
    parsers (_s / _usd / _side / _dt)."""
    df = event_df
    if df is None or df.empty or "Ticker" not in df.columns:
        return None
    from engine import altdata
    tk = df["Ticker"].map(altdata._s)
    mask = tk.isin(set(members))
    if not mask.any():
        return None
    sub = df[mask]
    covered = sorted({t for t in tk[mask].dropna()})
    if len(covered) < MIN_COVERED:
        return None
    dcol = next((c for c in src["date"] if c in sub.columns), None)
    vcol = next((c for c in src["value"] if c in sub.columns), None)
    if not dcol or not vcol:
        return None
    dt = altdata._dt(sub[dcol])
    t0 = pd.Timestamp(today) if today is not None else dt.max()
    if pd.isna(t0):
        return None
    rec = (dt > t0 - pd.Timedelta(days=QUIVER_RECENT_D)) & (dt <= t0)
    pri = (dt > t0 - pd.Timedelta(days=QUIVER_RECENT_D + QUIVER_PRIOR_D)) & (dt <= t0 - pd.Timedelta(days=QUIVER_RECENT_D))
    val = sub[vcol].map(altdata._usd)
    if src["signed"]:
        tcol = src.get("txn_col", "Transaction")
        if tcol in sub.columns:
            sgn = sub[tcol].map(lambda t: -1.0 if altdata._side(t) == "sell" else (1.0 if altdata._side(t) == "buy" else 0.0))
            val = val * sgn
    recent = float(np.nansum(val[rec].to_numpy(dtype=float)))
    prior = float(np.nansum(val[pri].to_numpy(dtype=float)))
    if src["signed"]:
        scale = max(abs(prior), abs(recent), 1.0)
        metric, accel = (recent - prior) / scale, None
    else:
        if prior < src.get("min_prior", 5e5) or prior <= 0:
            return None
        accel = float(np.clip(recent / prior, *ACCEL_CLAMP))
        metric = float(np.log(accel))
    return {"accel": None if accel is None else round(accel, 3),
            "recent_3m_usd": round(recent, 0), "base_3m_usd": round(prior, 0),
            "metric": float(metric), "n_covered": len(covered), "covered": covered}


def _theme_event_metric(src: dict, bid: str, *, frame: pd.DataFrame | None) -> dict | None:
    """Per-basket COUNT accel from a pre-aggregated theme_event frame (the collector already
    rolled members up to the basket). recent_count vs prior_count over the collector's window.
    Counts, not dollars: a new-from-nothing burst (prior 0, recent>0) reads as strong accel
    (clamped); both-zero is SILENT (None, not a spurious negative). Unsigned only."""
    if frame is None or frame.empty or bid not in frame.index:
        return None
    row = frame.loc[bid]

    def _num(col):
        try:
            v = float(row.get(col))
            return v if np.isfinite(v) else 0.0
        except (TypeError, ValueError):
            return 0.0

    recent, prior = _num("recent_count"), _num("prior_count")
    if recent <= 0 and prior <= 0:
        return None  # no activity either window — silent on the diagonal
    floor = float(src.get("min_prior", 1.0))            # avoid /0 + tiny-denom blow-ups
    accel = float(np.clip(recent / max(prior, floor), *ACCEL_CLAMP))
    covered = []
    cov = row.get("covered") if "covered" in frame.columns else None
    if isinstance(cov, str) and cov:
        covered = [c for c in cov.split(",") if c]
    try:
        n_cov = int(row.get("n_members")) if "n_members" in frame.columns else len(covered)
    except (TypeError, ValueError):
        n_cov = len(covered)
    return {"accel": round(accel, 3), "recent_3m_usd": None, "base_3m_usd": None,
            "metric": float(np.log(accel)) if accel > 0 else 0.0,
            "recent_count": int(recent), "prior_count": int(prior),
            "n_covered": max(n_cov, int(recent)), "covered": covered}


def pipeline_to_award_ratio(basket_id: str, members: list[str],
                             opp_frame: pd.DataFrame | None,
                             oblig_wide: pd.DataFrame | None,
                             *, lag_months: int | None = None) -> dict | None:
    """Count-based SAM->USAspending pipeline conversion context per basket.

    Joins SAM solicitation counts (opp_frame, basket-indexed) at time T to the USAspending
    obligation dollars that materialised approximately lag_months later for the same basket.
    Returns a display-only dict — NEVER enters fused_obs_z (lag is a labeled assumption,
    not backtested; per R9c, this is count-based because SAM dollar values are ~20-30%
    populated on presolicitations).

    Returns None when either input is absent, basket is not in opp_frame, or history is
    too thin for the lag window."""
    if opp_frame is None or oblig_wide is None:
        return None
    if opp_frame.empty or basket_id not in opp_frame.index:
        return None
    try:
        opp_count = float(opp_frame.loc[basket_id, "recent_count"] or 0)
    except (KeyError, TypeError, ValueError):
        return None
    if opp_count <= 0:
        return None
    lag = lag_months if lag_months is not None else PIPELINE_LAG_MONTHS.get(
        basket_id, PIPELINE_LAG_MONTHS["_default"])
    cols = [c for c in members if c in oblig_wide.columns]
    if len(cols) < MIN_COVERED:
        return None
    monthly = oblig_wide[cols].sum(axis=1, min_count=1).dropna().sort_index()
    # Slice the lagged award window: months that would correspond to the prior SAM 90d window
    # offset by `lag` months back from the most-recent complete month.
    # After LAG_MONTHS trim the usable tail is monthly[-1]; the lagged window is
    # months[-(LAG_MONTHS + lag + RECENT_MONTHS):-(LAG_MONTHS + lag)] but we use the raw
    # (un-trimmed) frame here so the slice is: months[-(lag + RECENT_MONTHS):-lag].
    if len(monthly) < lag + RECENT_MONTHS + 1:
        return None
    lag_window = monthly.iloc[-(lag + RECENT_MONTHS):-lag]
    if len(lag_window) < 2:
        return None
    award_usd = float(lag_window.sum())
    if award_usd < MIN_BASE_USD:
        return None
    return {
        "opp_count_recent": int(opp_count),
        "award_usd_lagged": round(award_usd, 0),
        "award_per_opp_usd": round(award_usd / opp_count, 0),
        "lag_months_assumption": lag,
        "n_cols": len(cols),
    }


def _load_new_program_events(root=None) -> dict[str, list[dict]]:
    """Load the program ledger parquet (first-seen NAICS/CFDA per basket).

    Returns {basket_id: [event, ...]} where each event has keys: naics_or_cfda, source,
    first_seen_date, title.  The ledger is written by collectors (sam_gov / grants_gov) at
    collect time; absent file -> returns {} gracefully (no error).

    Limitation: collectors do not yet persist per-opportunity code identity (only aggregated
    counts), so the ledger only populates once that collector-side hook is active.  This
    function activates when the file appears — callers need not change."""
    try:
        data_dir = Path(root) if root else config.data_dir()
        p = data_dir / "theme_activity" / "program_ledger.parquet"
        if not p.exists():
            return {}
        df = pd.read_parquet(p)
        if df.empty or "basket_id" not in df.columns:
            return {}
        result: dict[str, list[dict]] = {}
        for _, row in df.iterrows():
            bid = str(row["basket_id"])
            result.setdefault(bid, []).append({
                k: row[k] for k in df.columns if k != "basket_id"
            })
        return result
    except Exception as e:  # noqa: BLE001
        log.debug("program_ledger load failed: %s", e)
        return {}


def compute_real_activity(baskets_payload: dict, *, sources_data: dict | None = None,
                          root=None, news: bool = True, today=None) -> dict:
    """Per-basket fused real-activity observable. Returns {basket_id: {...}} for every
    basket with >=1 usable source. Two-pass: per-source raw metrics, then cross-sectional
    robust-z + weight fusion. Pure-ish: inject sources_data for hermetic tests.

    W0d extensions (NOTE: rr_surprise DOES enter fused_obs_z — it blends into the usaspending
    leg metric at RR_WEIGHT before the cross-sectional z, by design; only pipeline_to_award and
    new_programs are display-only and outside the fused paths):
      out[bid]["primary"]["rr_surprise"]    — run-rate ratio (recent / trailing avg); None if gated
      out[bid]["primary"]["rr_sept_gated"] — True if Sep/Oct gate zeroed rr blend this month
      out[bid]["pipeline_to_award"]        — SAM->USAspending count context dict or None
      out[bid]["new_programs"]             — list of first-seen NAICS/CFDA events (max 5)"""
    baskets = (baskets_payload or {}).get("baskets") or []
    if not baskets:
        return {}

    # pass 1 — per-basket, per-source raw metrics. Preload each source once by kind: 'wide'
    # sources are date-indexed store frames (YoY); 'quiver' sources are main's event tables
    # (recent window); 'theme_event' sources are pre-aggregated per-basket count frames.
    loaded = {src["name"]: _load_for(src, sources_data) for src in SOURCES}
    events = None
    if news:
        try:
            from engine import news_flow
            events = news_flow.load_events(root=root)
        except Exception as e:  # noqa: BLE001
            log.debug("news events load failed: %s", e)

    # W0d: load program ledger once (graceful absent)
    new_prog_events = _load_new_program_events(root=root)

    raw: dict[str, dict] = {}
    for b in baskets:
        bid = b.get("id")
        members = _live_members(b)
        per_src = {}
        for src in SOURCES:
            data = loaded.get(src["name"])
            if data is None:
                continue
            if src["kind"] == "wide":
                acc = source_accel(data, members, signed=src["signed"], min_base=src["min_base"],
                                   recent_months=src.get("recent_months", RECENT_MONTHS),
                                   seasonal=src.get("seasonal", True))
            elif src["kind"] == "theme_event":
                acc = _theme_event_metric(src, bid, frame=data)
            else:
                acc = _quiver_basket_metric(src, members, today=today, event_df=data)
            if acc is not None:
                per_src[src["name"]] = acc
        news_leg = None
        if news and events is not None:
            try:
                from engine import news_flow
                news_leg = news_flow.theme_flow(bid, events, today=today)
            except Exception as e:  # noqa: BLE001
                log.debug("news leg failed for %s: %s", bid, e)
        # require >=1 HARD source (spend / alt-data); the coarse news leg only ENRICHES a
        # basket that already has hard activity data — it never qualifies one on its own.
        if per_src:
            raw[bid] = {"sources": per_src, "news": news_leg, "members": members}

    if not raw:
        return {}

    # pass 2 — cross-sectional robust-z per source, then weight-fuse
    bids = list(raw)
    z_by_src: dict[str, dict[str, float]] = {}
    for src in SOURCES:
        metrics = [raw[bid]["sources"].get(src["name"], {}).get("metric") for bid in bids]
        zs = robust_z([m if m is not None else np.nan for m in metrics])
        z_by_src[src["name"]] = {bid: z for bid, z in zip(bids, zs)}
    news_metrics = [(raw[bid]["news"] or {}).get("metric") for bid in bids]
    news_z = {bid: z for bid, z in zip(bids, robust_z([m if m is not None else np.nan for m in news_metrics]))}

    weight = {src["name"]: src["weight"] for src in SOURCES}
    out: dict[str, dict] = {}
    for bid in bids:
        present = raw[bid]["sources"]
        members = raw[bid]["members"]
        leg_list, num, den = [], 0.0, 0.0
        ln_accel_num, ln_accel_den = 0.0, 0.0
        for src in SOURCES:
            nm = src["name"]
            if nm not in present:
                continue
            z = z_by_src[nm][bid]
            w = weight[nm]
            num += w * z
            den += w
            leg = {"name": nm, "label_en": src["label_en"], "label_zh": src["label_zh"],
                   "accel": present[nm]["accel"], "z": round(z, 3), "weight": w,
                   "n_covered": present[nm]["n_covered"], "covered": present[nm]["covered"]}
            leg_list.append(leg)
            if present[nm]["accel"] is not None and present[nm]["accel"] > 0:
                ln_accel_num += w * np.log(present[nm]["accel"])
                ln_accel_den += w
        news_leg = raw[bid]["news"]
        if news_leg is not None:
            z = news_z[bid]
            num += NEWS_WEIGHT * z
            den += NEWS_WEIGHT
            leg_list.append({"name": "news_velocity", "label_en": "News flow", "label_zh": "新闻流",
                             "velocity": news_leg["velocity"], "acceleration": news_leg["acceleration"],
                             "z": round(z, 3), "weight": NEWS_WEIGHT,
                             "unscheduled_share": news_leg["unscheduled_share"], "tier1_share": news_leg["tier1_share"]})
        if den <= 0:
            continue
        fused_obs_z = num / den
        fused_accel = float(np.exp(ln_accel_num / ln_accel_den)) if ln_accel_den > 0 else None
        if fused_accel is not None:
            obs_dir = 1 if fused_accel >= ACCEL_UP else (-1 if fused_accel <= ACCEL_DOWN else 0)
        else:
            obs_dir = 1 if fused_obs_z >= 0.75 else (-1 if fused_obs_z <= -0.75 else 0)
        primary = present.get("usaspending") or next(iter(present.values()), None)

        # W0d: pipeline-to-award context (display-only; opp_frame from sam_presolicitation)
        opp_frame = loaded.get("sam_presolicitation")
        oblig_wide = loaded.get("usaspending")
        pta = pipeline_to_award_ratio(bid, members, opp_frame, oblig_wide)

        out[bid] = {
            "fused_obs_z": round(fused_obs_z, 3),
            "fused_accel": None if fused_accel is None else round(fused_accel, 3),
            "obs_dir": obs_dir,
            "n_sources": len(present) + (1 if news_leg is not None else 0),
            "sources": leg_list,
            "primary": None if primary is None else {
                "accel": primary["accel"], "recent_3m_usd": primary["recent_3m_usd"],
                "base_3m_usd": primary["base_3m_usd"], "n_covered": primary["n_covered"],
                "covered": primary["covered"],
                # W0d: rr_surprise display fields (None when gated or absent)
                "rr_surprise": primary.get("rr_surprise"),
                "rr_sept_gated": primary.get("rr_sept_gated", False),
            },
            "news": news_leg,
            # W0d display-only extensions
            "pipeline_to_award": pta,
            "new_programs": new_prog_events.get(bid, [])[-5:],
        }
    return out
