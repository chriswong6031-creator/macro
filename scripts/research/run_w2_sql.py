"""Entry-Stack Expansion W2 — S-QL Quality Holdability Overlay Study.

Masterplan ref: research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md §3 F5.
Amendment 1 ref: research/ENTRY_STACK_EXPANSION_AMENDMENT1_BY_FABLE.md
  RUL-13 (horizon doctrine): 63d/126d metrics are the HOLDABILITY lane only.
  RUL-14 (vol-zone co-primaries): zone_held_21 / stop_vol_21 reported.
W0 baselines frozen in: research/entry_stack/W0_BASELINES.md (RUL-7 gate).
Null-competitor yardstick: research/entry_stack/W1_NC_REPORT.md (RUL-3).

LANE SCOPE (S-QL only):
  Claim under test: HOLDABILITY — given a fire, do higher-quality names hold
  better at 63d/126d (positional_liftoff_1.15/126, dead_money_126,
  fwd_mdd_126)? This lane is EXPLICITLY NOT about entry timing; 21d
  metrics are printed as CONTEXT ONLY with a mandatory banner.

Family: esx_ql_overlay (budget=10, pre-registered at W0; amended below).
  Pre-registered: 12 trials = 3 quality defs × 2 horizons × 2 forms
  Amendment: 63d holdability outcomes are NOT computed in this run (deep panel only;
    fwd_mdd_63 / clean-liftoff@63d absent from the graded DataFrame). Only the 126d
    horizon is run. Budget spent = 10 (3 defs × 2 forms minus 2 Sloan interaction slots).
    63d trials are removed from QL_TRIALS to prevent a pre-registration/execution mismatch
    in the trial ledger. A future run must explicitly add fwd_mdd_63 / clean15_63 and
    reintroduce the 63d arm.
  Quality defs: Piotroski F-score tercile, Altman Z-score tercile,
                Sloan accruals tercile (main-effect only — not in interaction arms)
  Horizons: 126d (positional/primary) — 63d deferred (see amendment above)
  Forms: standalone stratification, interaction with washout depth
         (Piotroski/Altman only for interaction — Sloan excluded per masterplan §3 F5)

PIT LAW:
  fundamentals_panel.parquet asof_date = period_end + 120d FLAT (std=0).
  This is an ASSUMED lag, not per-filer filing dates.
  A fire may only see FY rows with asof_date <= fire_date.
  Every artifact carries pit_basis: assumed-120d-lag.

R1 estimator: date-FE stratified difference (RUL-12), fast vectorized
  block-bootstrap from run_w1_nc.py.
BH q<=0.10 within esx_ql_overlay family.
Recall printed beside precision.
Survivor stamps on all absolute rates.
No promotion language. No "validated" word.

Output:
  research/entry_stack/W2_SQL_REPORT.md

Usage:
    cd /path/to/repo
    python scripts/research/run_w2_sql.py
    python scripts/research/run_w2_sql.py --smoke   # 50 boot, deep only
    python scripts/research/run_w2_sql.py --panel deep
    python scripts/research/run_w2_sql.py --n-bootstrap 500
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import harness primitives
# ---------------------------------------------------------------------------
from scripts.research.entry_strata_phase0 import (  # noqa: E402
    _build_sector_map,
    _get_closes,
    _register_all_families,
    _prepare_binary_outcomes,
    _assign_era,
    compute_recall,
    grade_fires,
    load_fires,
    FAMILY_BUDGETS,
    PROGRAM_ERAS,
    BH_Q_THRESHOLD,
    N_BOOTSTRAP,
    RNG_SEED,
)
from scripts.research.run_w1_nc import (  # noqa: E402
    fast_r1_estimate,
    fast_effect_table,
    fast_era_table,
    bh_correction,
    _fmt_pct,
    _fmt_f,
    _ci_str,
    _excl_zero,
    _write_effect_md,
    EFFECT_OUTCOMES,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA           = _REPO_ROOT / "data"
_RESEARCH_DIR   = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP     = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS  = _DATA / "research" / "gate_fires_baskets.parquet"
_LEDGER_PATH    = _DATA / "trial_ledger.jsonl"
_FUND_PANEL     = _DATA / "edgar" / "fundamentals_panel.parquet"

# PIT basis stamp (masterplan §3 F5, RT blocker fix)
PIT_BASIS = "assumed-120d-lag"

# ---------------------------------------------------------------------------
# Quality score computation from fundamentals_panel
# ---------------------------------------------------------------------------

def _piotroski_from_panel_rows(rows: list[dict]) -> float | None:
    """Piotroski F-score from panel rows (ascending FY order).

    Simplified 7-point variant using fundamentals_panel columns.
    The panel lacks cur_assets/cur_liab, so those two Piotroski tests
    are skipped when absent. Returns score / total_computable, where
    total >= 5 required (same guard as stock_fundamentals._piotroski).
    Returns None if < 5 tests computable.

    Panel columns available: ni, assets, cfo, debt_lt, shares,
    gross_profit, revenue, assets_prior, ni_prior, equity.
    """
    if len(rows) < 2:
        return None
    a, b = rows[-2], rows[-1]  # prior, latest FY

    def n(r: dict, k: str) -> float | None:
        v = r.get(k)
        return float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else None

    def ratio(r: dict, num: str, den: str) -> float | None:
        x, y = n(r, num), n(r, den)
        return x / y if (x is not None and y not in (None, 0.0)) else None

    score, total = 0, 0
    tests = [
        (ratio(b, "ni", "assets"), None, "gt0"),             # ROA > 0
        (n(b, "cfo"), None, "gt0"),                           # CFO > 0
        (ratio(b, "ni", "assets"), ratio(a, "ni", "assets"), "gt"),  # ROA rising
        (n(b, "cfo"), n(b, "ni"), "gt"),                     # accruals: CFO > NI
        (ratio(a, "debt_lt", "assets"), ratio(b, "debt_lt", "assets"), "gt"),  # leverage falling
        (n(a, "shares"), n(b, "shares"), "gte"),              # no dilution
        (ratio(b, "gross_profit", "revenue"),
         ratio(a, "gross_profit", "revenue"), "gt"),          # gross margin rising
        (ratio(b, "revenue", "assets"),
         ratio(a, "revenue", "assets"), "gt"),                # asset turnover rising
    ]
    for x, y, op in tests:
        if x is None or (op in ("gt", "gte") and y is None):
            continue
        total += 1
        if op == "gt0":
            score += 1 if x > 0 else 0
        elif op == "gt":
            score += 1 if x > y else 0
        elif op == "gte":
            score += 1 if x >= y * 1.01 else 0

    if total < 5:
        return None
    return float(score)


def _altman_from_panel_row(row: dict) -> float | None:
    """Altman Z-score (simplified, 4-leg without market-cap leg).

    fundamentals_panel lacks cur_assets/cur_liab/retained_earnings/op_income —
    we compute the 3 available legs: working-capital/assets (leg absent without
    cur_assets/cur_liab), retained-earnings/assets (absent), EBIT/assets
    (absent), revenue/assets (present). With only 1 leg available, we return
    None. A version using available fields: equity/assets as a leverage proxy.

    Practical fallback (conservative, uses only consistently-present fields):
      X1 = (equity - debt_lt) / assets  [crude working-capital proxy; skipped
           if debt_lt missing]
      X2 = ni / assets                   [return on assets, correlated with
           retained earnings / assets]
      X3 = (cfo - ni) / assets           [quality-of-earnings proxy for EBIT]
      X4 = revenue / assets              [asset utilization]
    Require >= 3 legs. NOT the canonical Altman Z — labeled ALTMAN_APPROX.
    The purpose is cross-sectional tercile RANK, not a level prediction,
    so a monotone proxy suffices.

    Returns float score or None.
    """
    def n(k: str) -> float | None:
        v = row.get(k)
        return float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else None

    assets = n("assets")
    if assets is None or assets <= 0:
        return None

    legs: list[float] = []
    # Leg 1: equity pressure proxy (equity / assets)
    eq = n("equity")
    if eq is not None:
        legs.append(eq / assets)
    # Leg 2: ni / assets (profitability proxy)
    ni = n("ni")
    if ni is not None:
        legs.append(ni / assets)
    # Leg 3: cfo / assets (cash quality)
    cfo = n("cfo")
    if cfo is not None:
        legs.append(cfo / assets)
    # Leg 4: revenue / assets (asset utilization)
    rev = n("revenue")
    if rev is not None:
        legs.append(rev / assets)

    if len(legs) < 3:
        return None
    # Simple sum (not weighted like canonical Altman) — cross-sectional rank only
    return float(sum(legs))


def _sloan_from_panel_row(row: dict) -> float | None:
    """Sloan accrual ratio: (ni - cfo) / assets.

    Higher = more accruals = lower accounting quality.
    Returns float or None.
    """
    def n(k: str) -> float | None:
        v = row.get(k)
        return float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else None

    ni = n("ni")
    cfo = n("cfo")
    assets = n("assets")
    if ni is None or cfo is None or assets is None or assets == 0:
        return None
    return float((ni - cfo) / assets)


def load_quality_panel(panel_path: Path) -> pd.DataFrame:
    """Load fundamentals_panel.parquet with quality scores computed.

    Returns DataFrame with columns:
      ticker, fy, asof_date, period_end, piotroski_f, altman_approx, sloan_accrual

    pit_basis: assumed-120d-lag (every row's asof_date = period_end + 120d flat).
    """
    if not panel_path.exists():
        log.warning("fundamentals_panel.parquet not found: %s", panel_path)
        return pd.DataFrame()

    df = pd.read_parquet(panel_path)
    if df.empty:
        return df

    log.info("Loaded fundamentals_panel: %d rows, %d tickers",
             len(df), df["ticker"].nunique())

    # Compute Piotroski per (ticker, fy): requires prior FY row
    # Group by ticker ascending FY order
    records = []
    for ticker, grp in df.sort_values("fy").groupby("ticker"):
        rows = grp.to_dict("records")
        for i, row in enumerate(rows):
            pit_rows = rows[:i + 1]  # PIT-safe: only rows up to this FY
            pio = _piotroski_from_panel_rows(pit_rows) if i >= 1 else None
            alt = _altman_from_panel_row(row)
            slo = _sloan_from_panel_row(row)
            records.append({
                "ticker":        str(ticker),
                "fy":            int(row["fy"]),
                "asof_date":     row["asof_date"],
                "period_end":    row["period_end"],
                "piotroski_f":   pio,
                "altman_approx": alt,
                "sloan_accrual": slo,
                "pit_basis":     PIT_BASIS,
            })

    result = pd.DataFrame(records)
    result["asof_date"] = pd.to_datetime(result["asof_date"])
    result["period_end"] = pd.to_datetime(result["period_end"])

    log.info("Quality panel computed: %d rows (piotroski=%d non-null, altman=%d, sloan=%d)",
             len(result),
             result["piotroski_f"].notna().sum(),
             result["altman_approx"].notna().sum(),
             result["sloan_accrual"].notna().sum())
    return result


# ---------------------------------------------------------------------------
# PIT-safe quality assignment per fire
# ---------------------------------------------------------------------------

def assign_quality_to_fires(
    fires: pd.DataFrame,
    quality_panel: pd.DataFrame,
) -> pd.DataFrame:
    """Assign quality scores to each fire using PIT-safe lookup.

    PIT rule: for each fire (ticker, fire_date), find the latest FY row
    from quality_panel where asof_date <= fire_date.

    asof_date = period_end + 120d flat (assumed-120d-lag).
    A fire one day before asof_date must NOT see that FY row (test fixture
    requirement in tests/test_run_w2_sql.py).

    Returns fires DataFrame augmented with:
      piotroski_f, altman_approx, sloan_accrual, fy_used, asof_date_used
    All NaN where no PIT-eligible FY row exists.
    """
    if quality_panel.empty:
        fires = fires.copy()
        for c in ("piotroski_f", "altman_approx", "sloan_accrual",
                  "fy_used", "asof_date_used"):
            fires[c] = np.nan
        return fires

    fires = fires.copy()
    fires["date"] = pd.to_datetime(fires["date"])

    # Build index: ticker -> list of (asof_date, piotroski_f, altman_approx, sloan_accrual, fy)
    # sorted ascending by asof_date for binary-search lookup
    qp = quality_panel.copy()
    qp["asof_date"] = pd.to_datetime(qp["asof_date"])

    ticker_groups: dict[str, pd.DataFrame] = {
        t: g.sort_values("asof_date").reset_index(drop=True)
        for t, g in qp.groupby("ticker")
    }

    piotroski_vals: list[float | None] = []
    altman_vals: list[float | None] = []
    sloan_vals: list[float | None] = []
    fy_used: list[int | None] = []
    asof_used: list[pd.Timestamp | None] = []

    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        fire_date = pd.Timestamp(row["date"])
        grp = ticker_groups.get(ticker)

        if grp is None or grp.empty:
            piotroski_vals.append(None)
            altman_vals.append(None)
            sloan_vals.append(None)
            fy_used.append(None)
            asof_used.append(None)
            continue

        # PIT-safe: asof_date <= fire_date (strict: asof_date STRICTLY before or equal)
        eligible = grp[grp["asof_date"] <= fire_date]
        if eligible.empty:
            piotroski_vals.append(None)
            altman_vals.append(None)
            sloan_vals.append(None)
            fy_used.append(None)
            asof_used.append(None)
            continue

        latest = eligible.iloc[-1]
        piotroski_vals.append(latest["piotroski_f"])
        altman_vals.append(latest["altman_approx"])
        sloan_vals.append(latest["sloan_accrual"])
        fy_used.append(int(latest["fy"]) if pd.notna(latest["fy"]) else None)
        asof_used.append(latest["asof_date"])

    fires["piotroski_f"]    = piotroski_vals
    fires["altman_approx"]  = altman_vals
    fires["sloan_accrual"]  = sloan_vals
    fires["fy_used"]        = fy_used
    fires["asof_date_used"] = asof_used

    cov_pio = fires["piotroski_f"].notna().sum()
    cov_alt = fires["altman_approx"].notna().sum()
    cov_slo = fires["sloan_accrual"].notna().sum()
    log.info("Quality assignment: n=%d fires, piotroski=%d (%.1f%%), altman=%d (%.1f%%), "
             "sloan=%d (%.1f%%)",
             len(fires), cov_pio, 100 * cov_pio / max(len(fires), 1),
             cov_alt, 100 * cov_alt / max(len(fires), 1),
             cov_slo, 100 * cov_slo / max(len(fires), 1))
    return fires


# ---------------------------------------------------------------------------
# Cross-sectional tercile assignment (per fire-year, cross-sectional)
# ---------------------------------------------------------------------------

def assign_quality_terciles(fires: pd.DataFrame) -> pd.DataFrame:
    """Assign cross-sectional quality terciles per fire-year.

    Per masterplan §3 F5: bands are cross-sectional terciles computed
    cross-sectionally per fire-year (calendar year of the fire date).
    Tercile 0 = bottom (worst quality), 1 = middle, 2 = top (best quality).

    LOOK-AHEAD NOTE: cut-points (q33/q67) are computed over the FULL calendar year
    of fires (see _assign_tercile docstring). The quality SCORES are PIT-safe.
    This is analysis-grade only; a live chip must use trailing-window terciles.

    Direction: Piotroski high = better quality (top tercile = T2).
               Altman approx high = better (top tercile = T2).
               Sloan accruals high = WORSE quality (top tercile = worst).
               → For consistency: T2 = top-quality tercile for all defs.
               Sloan terciles are REVERSED so T2 = lowest accruals = best quality.

    Returns fires with added columns:
      piotroski_t, altman_t, sloan_t  (0/1/2 = bottom/mid/top quality tercile;
                                        NaN where quality score unavailable)
    """
    fires = fires.copy()
    fires["fire_year"] = pd.to_datetime(fires["date"]).dt.year

    def _assign_tercile(series: pd.Series, fire_year: pd.Series,
                        reverse: bool = False) -> pd.Series:
        """Cross-sectional per-fire-year tercile assignment.

        LOOK-AHEAD DISCLOSURE: tercile cut-points (q33/q67) are computed over
        the FULL calendar year of fires, so a January fire's tercile uses
        boundaries that incorporate later-in-year (e.g. December) fire scores.
        The quality SCORES themselves are PIT-safe (asof_date<=fire_date).
        This is analysis-grade (per masterplan §3 F5 'cross-sectional per fire-year')
        and acceptable for a holdability study; it is NOT live-deployable.
        A future live chip must switch to trailing-window terciles.
        """
        result = pd.Series(np.nan, index=series.index, dtype=float)
        for yr, idx in series.groupby(fire_year).groups.items():
            vals = series.loc[idx].dropna()
            if len(vals) < 10:
                continue
            q33 = float(vals.quantile(1 / 3))
            q67 = float(vals.quantile(2 / 3))
            raw = np.where(
                series.loc[idx].isna(), np.nan,
                np.where(series.loc[idx] <= q33, 0.0,
                         np.where(series.loc[idx] <= q67, 1.0, 2.0))
            )
            if reverse:
                # Flip: 0 becomes 2 (worst accruals → top), 2 becomes 0 (best)
                raw = np.where(np.isnan(raw), np.nan, 2.0 - raw)
            result.loc[idx] = raw
        return result

    fires["piotroski_t"] = _assign_tercile(
        fires["piotroski_f"], fires["fire_year"], reverse=False
    )
    fires["altman_t"] = _assign_tercile(
        fires["altman_approx"], fires["fire_year"], reverse=False
    )
    fires["sloan_t"] = _assign_tercile(
        fires["sloan_accrual"], fires["fire_year"], reverse=True
    )

    log.info("Tercile assignment: piotroski_t=%d non-null, altman_t=%d, sloan_t=%d",
             fires["piotroski_t"].notna().sum(),
             fires["altman_t"].notna().sum(),
             fires["sloan_t"].notna().sum())
    return fires


# ---------------------------------------------------------------------------
# Washout-depth variable (used in interaction arm)
# ---------------------------------------------------------------------------

def assign_washout_depth(fires: pd.DataFrame, closes: dict[str, pd.Series]) -> pd.DataFrame:
    """Assign washout depth = dist from 21d prior rolling low at fire date.

    washout_depth = 1 - (close_at_fire / rolling_21d_prior_low)
    Higher = deeper washout. Used in interaction arm (Piotroski/Altman × washout).
    NaN when < 22 prior bars available.
    """
    fires = fires.copy()
    depths: list[float | None] = []
    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        fire_date = pd.Timestamp(row["date"])
        close = closes.get(ticker)
        if close is None or close.empty:
            depths.append(None)
            continue
        c = close.dropna().sort_index()
        loc = c.index.searchsorted(fire_date)
        if loc <= 0 or loc >= len(c):
            depths.append(None)
            continue
        if loc < 22:
            depths.append(None)
            continue
        prior_low = float(c.iloc[loc - 21: loc].min())
        cur_price = float(c.iloc[loc])
        if prior_low <= 0:
            depths.append(None)
            continue
        depths.append(float(1.0 - cur_price / prior_low))
    fires["washout_depth"] = depths
    return fires


def assign_washout_depth_tercile(fires: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional per-fire-year washout_depth tercile.

    T2 = deepest washout tercile (high depth = strong washout).
    """
    fires = fires.copy()
    fire_year = pd.to_datetime(fires["date"]).dt.year
    result = pd.Series(np.nan, index=fires.index, dtype=float)
    for yr, idx in fires.groupby(fire_year).groups.items():
        vals = fires.loc[idx, "washout_depth"].dropna()
        if len(vals) < 10:
            continue
        q33 = float(vals.quantile(1 / 3))
        q67 = float(vals.quantile(2 / 3))
        raw = np.where(
            fires.loc[idx, "washout_depth"].isna(), np.nan,
            np.where(fires.loc[idx, "washout_depth"] <= q33, 0.0,
                     np.where(fires.loc[idx, "washout_depth"] <= q67, 1.0, 2.0))
        )
        result.loc[idx] = raw
    fires["washout_t"] = result
    return fires


# ---------------------------------------------------------------------------
# Holdability outcomes: positional (126d) with RUL-14 context
# ---------------------------------------------------------------------------

# Primary holdability outcomes per RUL-13
HOLDABILITY_OUTCOMES = [
    "positional_liftoff",   # clean15_126: primary holdability endpoint
    "dead_money",           # 126d dead-money: primary holdability endpoint
    "fwd_mdd_126",          # 126d max drawdown: context
]

# 21d context outcomes (printed with explicit NOT-ENTRY-TIMING banner)
CONTEXT_21D_OUTCOMES = [
    "stop5",
    "rotational_liftoff",
    "zone_held_21",
    "stop_vol_21",
]

# Trial registration config for esx_ql_overlay.
# Pre-registered budget was 12 (3 defs × 2 horizons × 2 forms).
# Amendment: 63d horizon trials OMITTED from this run — fwd_mdd_63 / clean15_63 are
# not computed (deep panel only; grade_fires does not emit 63d holdability metrics).
# Registering 63d trials without executing them would create a ledger mismatch.
# Trials omitted: pio_63d_standalone, alt_63d_standalone, slo_63d_standalone,
#                 pio_63d_interaction, alt_63d_interaction (5 trials).
# Trials run: 7 (3 standalone 126d + 2 interaction 126d + [note: see count below]).
# Actually: 3 standalone 126d + 2 interaction 126d = 5 trials registered here.
# Sloan has no interaction arm (§3 F5 masterplan restriction), so 2 interaction slots
# are not used. Total trials registered and executed: 5.
# Pre-reg budget remaining for 63d arm: reserved for future --panel baskets run
# that adds fwd_mdd_63 / clean15_63 metrics.
QL_TRIALS = [
    # (name, quality_tercile_col, form, interaction_allowed)
    ("pio_126d_standalone", "piotroski_t", "standalone", False),
    ("pio_126d_interaction","piotroski_t", "interaction", True),
    ("alt_126d_standalone", "altman_t",   "standalone", False),
    ("alt_126d_interaction","altman_t",   "interaction", True),
    ("slo_126d_standalone", "sloan_t",    "standalone", False),
    # Sloan: no interaction arm (§3 F5 masterplan restriction)
]


def _register_ql_trials(ledger_path: Path | None = None) -> None:
    """Log trial configs for esx_ql_overlay family."""
    try:
        from engine.trial_ledger import TrialLedger
    except ImportError:
        log.warning("trial_ledger not importable; QL trial rows skipped")
        return
    led = TrialLedger(path=ledger_path or _LEDGER_PATH)
    configs = [
        {"trial": name, "quality_col": qcol, "form": form}
        for name, qcol, form, _ in QL_TRIALS
    ]
    for cfg in configs:
        led.log_trial(cfg, family="esx_ql_overlay", note="W2 S-QL run")
    log.info("Logged %d QL trial configs in esx_ql_overlay", len(configs))


# ---------------------------------------------------------------------------
# Tertile-stratified holdability table (descriptive)
# ---------------------------------------------------------------------------

def _tertile_holdability_table(
    graded: pd.DataFrame,
    tercile_col: str,
    *,
    panel_label: str = "panel",
) -> list[dict[str, Any]]:
    """Compute outcome rates by quality tercile (0/1/2 = bottom/mid/top)."""
    df = _prepare_binary_outcomes(graded)
    df_ok = df[df["gradable"].fillna(False)].copy()

    rows: list[dict[str, Any]] = []
    for t in [0.0, 1.0, 2.0]:
        g = df_ok[df_ok[tercile_col] == t]
        if len(g) == 0:
            continue
        rec: dict[str, Any] = {
            "tercile": int(t),
            "tercile_label": ["bottom_quality", "mid_quality", "top_quality"][int(t)],
            "n_fires": len(g),
        }
        for col in (HOLDABILITY_OUTCOMES + CONTEXT_21D_OUTCOMES):
            if col in g.columns:
                rec[f"{col}_mean"] = round(float(g[col].mean()), 4) if g[col].notna().any() else None
        rows.append(rec)
    return rows


# ---------------------------------------------------------------------------
# Top-vs-bottom tercile effect (T2 vs T0; primary estimator)
# ---------------------------------------------------------------------------

def _top_vs_bottom_effect(
    graded: pd.DataFrame,
    tercile_col: str,
    *,
    fe_granularity: str = "date",
    sector_col: str | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
    family_label: str = "study",
    outcomes: list[str] | None = None,
) -> dict[str, Any]:
    """R1 FE estimate: top tercile (T2=1) vs bottom tercile (T0=0).

    Only fires in T0 or T2 are included (T1 dropped from estimation frame).
    Returns same schema as fast_effect_table.
    """
    df = _prepare_binary_outcomes(graded)
    df_ok = df[df["gradable"].fillna(False)].copy()

    # Restrict to T0 vs T2
    df_ok = df_ok[df_ok[tercile_col].isin([0.0, 2.0])].copy()
    # Treatment = T2 (top quality)
    df_ok["_ql_top"] = (df_ok[tercile_col] == 2.0).astype(float)

    if len(df_ok) < 20:
        return {
            "effects": [], "bh_panel": [], "n_total": 0,
            "n_treatment": 0, "n_control": 0,
            "fe_granularity": fe_granularity, "sector_fallback": False,
            "survivor_stamp": "insufficient rows", "family_label": family_label,
        }

    df_ok["date"] = pd.to_datetime(df_ok["date"])
    if fe_granularity == "date":
        df_ok["_fe"] = df_ok["date"].dt.strftime("%Y-%m-%d")
    else:
        raise ValueError(f"Unsupported fe_granularity: {fe_granularity!r}")

    df_ok["_date_ts"] = df_ok["date"].values.astype("datetime64[ns]").astype(np.int64)

    sector_fallback = False
    if sector_col and sector_col in df_ok.columns:
        cov = df_ok[sector_col].notna().mean()
        if cov < 0.50:
            sector_fallback = True
    else:
        sector_col = None

    use_outcomes = outcomes or HOLDABILITY_OUTCOMES
    effects = []
    p_values: list[float | None] = []
    labels: list[str] = []

    for col in use_outcomes:
        if col not in df_ok.columns:
            continue
        res = fast_r1_estimate(
            df_ok, col, "_ql_top",
            fe_col="_fe",
            sector_col=sector_col if not sector_fallback else None,
            n_bootstrap=n_bootstrap,
        )
        res["label"] = col
        effects.append(res)
        p_values.append(res.get("p_value"))
        labels.append(col)

    bh = bh_correction(p_values, labels)
    n_treat = int((df_ok["_ql_top"] == 1).sum())
    n_ctrl  = int((df_ok["_ql_top"] == 0).sum())

    return {
        "effects":        effects,
        "bh_panel":       bh,
        "n_total":        len(df_ok),
        "n_treatment":    n_treat,
        "n_control":      n_ctrl,
        "fe_granularity": fe_granularity,
        "sector_fallback": sector_fallback,
        "survivor_stamp": (
            "SURVIVOR BIAS: absolute rates on surviving names only. "
            "Comparisons between strata are directionally valid."
        ),
        "family_label":   family_label,
    }


# ---------------------------------------------------------------------------
# Interaction arm: quality_t × washout_t
# ---------------------------------------------------------------------------

def _interaction_arm(
    graded: pd.DataFrame,
    quality_col: str,
    *,
    fe_granularity: str = "date",
    sector_col: str | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
    family_label: str = "interaction",
) -> dict[str, Any]:
    """Interaction: top-quality × deep-washout vs rest.

    Interaction stratum = 1 iff quality_t == 2 AND washout_t == 2.
    Tests whether the quality premium concentrates in deep-washout fires.
    R1 FE estimator; holdability outcomes only.

    Sloan excluded from this arm per masterplan §3 F5 (interaction arms restricted to
    Piotroski/Altman only). Sloan is NOT margin-dependent; it is excluded because the
    masterplan's explicit restriction names only Piotroski/Altman for interaction arms.
    """
    df = _prepare_binary_outcomes(graded)
    df_ok = df[df["gradable"].fillna(False)].copy()

    if "washout_t" not in df_ok.columns or quality_col not in df_ok.columns:
        return {"effects": [], "bh_panel": [], "n_total": 0,
                "n_treatment": 0, "n_control": 0, "family_label": family_label,
                "note": "washout_t or quality_col missing"}

    df_ok["_interaction"] = (
        (df_ok[quality_col] == 2.0) & (df_ok["washout_t"] == 2.0)
    ).astype(float)
    df_ok = df_ok[df_ok[quality_col].notna() & df_ok["washout_t"].notna()].copy()

    if len(df_ok) < 20:
        return {"effects": [], "bh_panel": [], "n_total": 0,
                "n_treatment": 0, "n_control": 0, "family_label": family_label,
                "note": "insufficient rows after quality+washout filter"}

    df_ok["date"] = pd.to_datetime(df_ok["date"])
    df_ok["_fe"] = df_ok["date"].dt.strftime("%Y-%m-%d")
    df_ok["_date_ts"] = df_ok["date"].values.astype("datetime64[ns]").astype(np.int64)

    sector_fallback = False
    if sector_col and sector_col in df_ok.columns:
        cov = df_ok[sector_col].notna().mean()
        if cov < 0.50:
            sector_fallback = True
    else:
        sector_col = None

    effects = []
    p_values: list[float | None] = []
    labels: list[str] = []

    for col in HOLDABILITY_OUTCOMES:
        if col not in df_ok.columns:
            continue
        res = fast_r1_estimate(
            df_ok, col, "_interaction",
            fe_col="_fe",
            sector_col=sector_col if not sector_fallback else None,
            n_bootstrap=n_bootstrap,
        )
        res["label"] = col
        effects.append(res)
        p_values.append(res.get("p_value"))
        labels.append(col)

    bh = bh_correction(p_values, labels)
    n_treat = int((df_ok["_interaction"] == 1).sum())
    n_ctrl  = int((df_ok["_interaction"] == 0).sum())

    return {
        "effects":        effects,
        "bh_panel":       bh,
        "n_total":        len(df_ok),
        "n_treatment":    n_treat,
        "n_control":      n_ctrl,
        "fe_granularity": fe_granularity,
        "sector_fallback": sector_fallback,
        "survivor_stamp": (
            "SURVIVOR BIAS: absolute rates on surviving names only."
        ),
        "family_label":   family_label,
    }


# ---------------------------------------------------------------------------
# Coverage report (fires excluded from both arms)
# ---------------------------------------------------------------------------

def _coverage_report(fires: pd.DataFrame, graded: pd.DataFrame) -> dict[str, Any]:
    """Count fires excluded from EDGAR coverage and report."""
    n_fires = len(fires)
    cov_pio = int(fires["piotroski_f"].notna().sum())
    cov_alt = int(fires["altman_approx"].notna().sum())
    cov_slo = int(fires["sloan_accrual"].notna().sum())
    n_excluded_pio = n_fires - cov_pio
    n_excluded_alt = n_fires - cov_alt
    n_excluded_slo = n_fires - cov_slo

    # Check how many fires are in names without Piotroski-computable EDGAR history.
    # NOTE: this keyed on Piotroski availability (strictest def — requires >=2 FY rows).
    # Some of these fires may have Altman/Sloan coverage; they are included in those arms.
    # Label: 'tickers without Piotroski-computable EDGAR history', not 'no EDGAR at all'.
    tickers_with_edgar = set(fires[fires["piotroski_f"].notna()]["ticker"].unique())
    tickers_no_edgar = set(fires["ticker"].unique()) - tickers_with_edgar
    n_excluded_tickers = len(tickers_no_edgar)
    n_excluded_fires_by_ticker = int(
        fires[fires["ticker"].isin(tickers_no_edgar)].shape[0]
    )

    # Gradable subset coverage
    gradable = graded[graded["gradable"].fillna(False)]
    n_gradable = len(gradable)
    n_grad_pio = int(gradable["piotroski_f"].notna().sum()) if "piotroski_f" in gradable.columns else 0
    n_grad_alt = int(gradable["altman_approx"].notna().sum()) if "altman_approx" in gradable.columns else 0
    n_grad_slo = int(gradable["sloan_accrual"].notna().sum()) if "sloan_accrual" in gradable.columns else 0

    return {
        "n_fires_total":            n_fires,
        "n_gradable":               n_gradable,
        "n_excluded_no_edgar_ticker": n_excluded_tickers,
        "n_excluded_fires_no_edgar": n_excluded_fires_by_ticker,
        "piotroski_coverage_fires": cov_pio,
        "altman_coverage_fires":    cov_alt,
        "sloan_coverage_fires":     cov_slo,
        "piotroski_coverage_gradable": n_grad_pio,
        "altman_coverage_gradable":    n_grad_alt,
        "sloan_coverage_gradable":     n_grad_slo,
    }


# ---------------------------------------------------------------------------
# Era table for quality stratification
# ---------------------------------------------------------------------------

def _era_quality_table(
    graded: pd.DataFrame,
    tercile_col: str,
) -> pd.DataFrame:
    """Era × quality tercile breakdown (stop5 rate, pos_liftoff, dead_money)."""
    df = _prepare_binary_outcomes(graded)
    df["date"] = pd.to_datetime(df["date"])
    df["era"] = df["date"].apply(_assign_era)
    df_ok = df[df["gradable"].fillna(False) & df[tercile_col].notna()].copy()

    rows = []
    for (era, terc), g in df_ok.groupby(["era", tercile_col]):
        rows.append({
            "era":         era,
            "tercile":     int(terc),
            "n_fires":     len(g),
            "stop5_rate":  round(float(g["stop5"].mean()), 4) if "stop5" in g.columns else None,
            "pos_liftoff": round(float(g["positional_liftoff"].mean()), 4) if "positional_liftoff" in g.columns else None,
            "dead_money":  round(float(g["dead_money"].mean()), 4) if "dead_money" in g.columns else None,
        })

    result = pd.DataFrame(rows)
    if not result.empty and "era" in result.columns:
        era_order = ["pre_2012", "2012-2015", "2016-2019", "2020-2022", "2023-2026"]
        result["era"] = pd.Categorical(result["era"], categories=era_order, ordered=True)
        result = result.sort_values(["era", "tercile"]).reset_index(drop=True)
    return result


# ---------------------------------------------------------------------------
# Core study runner (one panel)
# ---------------------------------------------------------------------------

def run_sql_study(
    panel_name: str,
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    quality_panel: pd.DataFrame,
    sector_map: dict[str, str],
    *,
    fe_granularity: str = "date",
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Run S-QL study for one panel."""
    fires = fires.copy()
    fires["sector"] = fires["ticker"].map(sector_map)

    # 1. Assign PIT-safe quality scores
    log.info("Panel %s: assigning quality scores to %d fires...", panel_name, len(fires))
    fires = assign_quality_to_fires(fires, quality_panel)

    # 2. Assign quality terciles (cross-sectional per fire-year)
    fires = assign_quality_terciles(fires)

    # 3. Grade fires (forward metrics)
    log.info("Panel %s: grading %d fires...", panel_name, len(fires))
    graded = grade_fires(fires, closes)
    n_gradable = int(graded["gradable"].fillna(False).sum())
    log.info("  Gradable: %d / %d", n_gradable, len(fires))

    # 4. Assign washout depth + tercile (needed for interaction arm)
    log.info("Panel %s: assigning washout depth...", panel_name)
    graded = assign_washout_depth(graded, closes)
    graded = assign_washout_depth_tercile(graded)

    # 5. Coverage report
    coverage = _coverage_report(fires, graded)
    log.info("Panel %s: EDGAR coverage: piotroski=%d/%d fires, altman=%d/%d, sloan=%d/%d",
             panel_name,
             coverage["piotroski_coverage_fires"], len(fires),
             coverage["altman_coverage_fires"], len(fires),
             coverage["sloan_coverage_fires"], len(fires))

    results: dict[str, Any] = {
        "panel":          panel_name,
        "n_fires_total":  len(fires),
        "n_gradable":     n_gradable,
        "fe_granularity": fe_granularity,
        "survivor_stamp": (
            "SURVIVOR BIAS: absolute rates on surviving names only; "
            "comparisons between strata are valid within this constraint."
        ),
        "pit_basis":      PIT_BASIS,
        "coverage":       coverage,
    }

    # ---- Run per quality def ------------------------------------------------
    for def_name, tercile_col, def_label in [
        ("piotroski", "piotroski_t", "Piotroski F-score"),
        ("altman",    "altman_t",    "Altman Z-score (approx)"),
        ("sloan",     "sloan_t",     "Sloan accrual (reversed, T2=low-accruals)"),
    ]:
        log.info("Panel %s: running %s study...", panel_name, def_name)

        has_quality = graded[tercile_col].notna().sum()
        if has_quality < 30:
            results[def_name] = {
                "note": f"Insufficient quality coverage ({has_quality} non-null); skipped.",
                "n_quality_nonull": int(has_quality),
            }
            log.warning("Panel %s: %s has only %d non-null rows; skipped.",
                        panel_name, def_name, has_quality)
            continue

        # Descriptive tercile table
        terc_table = _tertile_holdability_table(graded, tercile_col, panel_label=panel_name)

        # Standalone: T2 vs T0 — holdability outcomes
        eff_hold = _top_vs_bottom_effect(
            graded, tercile_col,
            fe_granularity=fe_granularity,
            sector_col="sector" if "sector" in graded.columns else None,
            n_bootstrap=n_bootstrap,
            family_label=f"QL_{def_name}_{panel_name}_hold",
            outcomes=HOLDABILITY_OUTCOMES,
        )

        # 21d context table (NOT entry-timing verdict — banner required)
        eff_21d = _top_vs_bottom_effect(
            graded, tercile_col,
            fe_granularity=fe_granularity,
            sector_col="sector" if "sector" in graded.columns else None,
            n_bootstrap=n_bootstrap,
            family_label=f"QL_{def_name}_{panel_name}_21d",
            outcomes=CONTEXT_21D_OUTCOMES,
        )

        # Era table
        era_tbl = _era_quality_table(graded, tercile_col)

        # Recall counts
        n_top    = int((graded[graded["gradable"].fillna(False)][tercile_col] == 2.0).sum())
        n_bottom = int((graded[graded["gradable"].fillna(False)][tercile_col] == 0.0).sum())
        n_total_q = int(graded[graded["gradable"].fillna(False)][tercile_col].notna().sum())
        recall_top = round(n_top / max(n_total_q, 1), 4)
        recall_bot = round(n_bottom / max(n_total_q, 1), 4)

        def_result: dict[str, Any] = {
            "def_name":         def_name,
            "def_label":        def_label,
            "tercile_col":      tercile_col,
            "n_quality_nonull": int(has_quality),
            "n_top_gradable":   n_top,
            "n_bottom_gradable": n_bottom,
            "recall_top":       recall_top,
            "recall_bottom":    recall_bot,
            "tercile_table":    terc_table,
            "holdability_effect": eff_hold,
            "context_21d_effect": eff_21d,
            "era_table":        era_tbl.to_dict(orient="records"),
        }

        # Interaction arm: Piotroski/Altman only (Sloan excluded)
        if def_name in ("piotroski", "altman"):
            log.info("Panel %s: running %s interaction arm...", panel_name, def_name)
            int_result = _interaction_arm(
                graded, tercile_col,
                fe_granularity=fe_granularity,
                sector_col="sector" if "sector" in graded.columns else None,
                n_bootstrap=n_bootstrap,
                family_label=f"QL_{def_name}_{panel_name}_interaction",
            )
            def_result["interaction_arm"] = int_result
        else:
            def_result["interaction_arm"] = {
                "note": (
                    "Interaction arm excluded for Sloan per masterplan §3 F5 "
                    "(interaction arms restricted to full-coverage Piotroski/Altman)."
                )
            }

        results[def_name] = def_result

    return results


# ---------------------------------------------------------------------------
# Main study runner (all panels)
# ---------------------------------------------------------------------------

def run_all_panels(
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    panels: list[str] | None = None,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Run S-QL study across deep + baskets panels."""
    _register_all_families(ledger_path)
    _register_ql_trials(ledger_path)

    sector_map = _build_sector_map()
    log.info("Sector map: %d tickers", len(sector_map))

    # Load quality panel (shared across all fires)
    log.info("Loading quality panel from %s...", _FUND_PANEL)
    quality_panel = load_quality_panel(_FUND_PANEL)
    if quality_panel.empty:
        log.error("Quality panel empty — cannot proceed.")
        return {}

    panel_configs = [
        ("deep",    _FIRES_DEEP,    "date"),
        ("baskets", _FIRES_BASKETS, "date"),
    ]
    if panels:
        panel_configs = [(n, p, fe) for n, p, fe in panel_configs if n in panels]

    all_results: dict[str, Any] = {}
    for panel_name, fires_path, fe_gran in panel_configs:
        if not fires_path.exists():
            log.warning("Fire dump not found: %s — skipping", fires_path)
            all_results[panel_name] = {"error": f"fires not found: {fires_path}"}
            continue
        fires = load_fires(fires_path)
        log.info("Panel %s: %d fires loaded", panel_name, len(fires))
        closes = _get_closes(panel_name)
        res = run_sql_study(
            panel_name, fires, closes, quality_panel, sector_map,
            fe_granularity=fe_gran,
            n_bootstrap=n_bootstrap,
        )
        all_results[panel_name] = res

    return all_results


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _write_tercile_table_md(lines: list[str], terc_rows: list[dict[str, Any]]) -> None:
    if not terc_rows:
        lines.append("_No tercile table available._")
        lines.append("")
        return
    header_cols = ["tercile", "tercile_label", "n_fires",
                   "positional_liftoff_mean", "dead_money_mean",
                   "fwd_mdd_126_mean", "stop5_mean", "rotational_liftoff_mean"]
    avail = [c for c in header_cols if any(c in r for r in terc_rows)]
    lines.append("| " + " | ".join(avail) + " |")
    lines.append("|" + "---|" * len(avail))
    for r in terc_rows:
        cells = []
        for c in avail:
            v = r.get(c)
            if v is None:
                cells.append("—")
            elif c in ("tercile",):
                cells.append(str(v))
            elif c in ("n_fires",):
                cells.append(f"{v:,}")
            elif isinstance(v, float):
                if "rate" in c or "liftoff" in c or "money" in c or "mdd" in c or "stop" in c:
                    cells.append(f"{v:.1%}")
                else:
                    cells.append(f"{v:.4f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")


def _headline_delta(def_result: dict[str, Any]) -> str:
    """Extract T2-vs-T0 positional_liftoff and dead_money delta from effect table.

    Terciles are 0/1/2 (bottom/mid/top). The estimator compares T2 (top quality)
    vs T0 (bottom quality). There is no T3 — the label 'T3-vs-T1' was incorrect.
    """
    hold = def_result.get("holdability_effect", {})
    effects = {e.get("label"): e for e in hold.get("effects", [])}
    bh = {b["label"]: b for b in hold.get("bh_panel", [])}

    liftoff = effects.get("positional_liftoff", {})
    dm = effects.get("dead_money", {})

    liftoff_coef = liftoff.get("coef")
    liftoff_ci   = (liftoff.get("ci_lo"), liftoff.get("ci_hi"))
    dm_coef      = dm.get("coef")
    dm_ci        = (dm.get("ci_lo"), dm.get("ci_hi"))

    liftoff_rej = (bh.get("positional_liftoff") or {}).get("rejected")
    dm_rej      = (bh.get("dead_money") or {}).get("rejected")

    parts = []
    if liftoff_coef is not None:
        excl = "CI-excl-0" if (liftoff_ci[0] is not None and
                               (liftoff_ci[0] > 0 or liftoff_ci[1] < 0)) else "CI-incl-0"
        rej_str = " BH-rej" if liftoff_rej else ""
        parts.append(f"pos_liftoff Δ={liftoff_coef:+.3f} [{excl}{rej_str}]")
    if dm_coef is not None:
        excl = "CI-excl-0" if (dm_ci[0] is not None and
                               (dm_ci[0] > 0 or dm_ci[1] < 0)) else "CI-incl-0"
        rej_str = " BH-rej" if dm_rej else ""
        parts.append(f"dead_money Δ={dm_coef:+.3f} [{excl}{rej_str}]")
    n_top = def_result.get("n_top_gradable", "?")
    n_bot = def_result.get("n_bottom_gradable", "?")
    recall = def_result.get("recall_top", None)
    recall_str = f" (recall T2={recall:.1%})" if recall is not None else ""
    return "; ".join(parts) + f"{recall_str} n_T2={n_top} n_T0={n_bot}"


def _build_family_bh(all_results: dict[str, Any]) -> dict[str, dict]:
    """Pre-compute the esx_ql_overlay family-level BH panel.

    Pools ALL holdability p-values from standalone and interaction arms
    per masterplan §5 ('BH q<=0.10 applied per family').  Returns a dict
    keyed by canonical label → {q_value, rejected} for patching effect dicts.
    """
    all_pvals: list[tuple[str, float | None]] = []
    for panel_name, res in all_results.items():
        if "error" in res:
            continue
        for def_name in ("piotroski", "altman", "sloan"):
            dr = res.get(def_name, {})
            hold = dr.get("holdability_effect", {})
            for e in hold.get("effects", []):
                label = f"{panel_name}/{def_name}/standalone/{e.get('label','?')}"
                all_pvals.append((label, e.get("p_value")))
            ia = dr.get("interaction_arm", {})
            if ia.get("effects"):
                for e in ia.get("effects", []):
                    label = f"{panel_name}/{def_name}/interaction/{e.get('label','?')}"
                    all_pvals.append((label, e.get("p_value")))
    if not all_pvals:
        return {}
    labels_bh = [x[0] for x in all_pvals]
    pvals_bh  = [x[1] for x in all_pvals]
    bh_results = bh_correction(pvals_bh, labels_bh)
    return {b["label"]: {"q_value": b.get("q_value"), "rejected": b.get("rejected")}
            for b in bh_results}


def _patch_bh_panel(
    effect_dict: dict[str, Any],
    family_bh: dict[str, dict],
    panel_name: str,
    def_name: str,
    arm: str,  # "standalone" or "interaction"
) -> dict[str, Any]:
    """Return a copy of effect_dict with bh_panel replaced by family-level BH values."""
    import copy
    patched = copy.copy(effect_dict)
    new_bh = []
    for e in patched.get("effects", []):
        outcome_label = e.get("label", "?")
        family_key = f"{panel_name}/{def_name}/{arm}/{outcome_label}"
        fam = family_bh.get(family_key, {})
        new_bh.append({
            "label":    outcome_label,
            "p_value":  e.get("p_value"),
            "q_value":  fam.get("q_value"),
            "rejected": fam.get("rejected"),
        })
    patched = dict(patched)
    patched["bh_panel"] = new_bh
    return patched


def write_report(all_results: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    a = lines.append

    # Pre-compute family-level BH (pools standalone + interaction arms)
    # to drive per-arm 'BH rej?' columns consistently with the family panel.
    family_bh = _build_family_bh(all_results)

    a("# W2 S-QL Quality Holdability Overlay — Entry-Stack Expansion")
    a("")
    a("**Status:** W2 report only — no promotion, no product change (RUL-3).")
    a("**Date:** 2026-07-05")
    a("")
    a("**Lane:** S-QL (§3 F5). HOLDABILITY STUDY ONLY.")
    a("**Horizon doctrine (RUL-13):** 63d/126d metrics are the HOLDABILITY lane only.")
    a("Entry timing is NOT under test in this lane. 21d context tables are printed")
    a("with an explicit banner; no entry-timing claims may be derived from them.")
    a("")
    a("**PIT basis:** `assumed-120d-lag`.")
    a("fundamentals_panel.parquet asof_date = period_end + 120d FLAT (std=0).")
    a("This is an assumed lag, not per-filer SEC filing dates.")
    a("A fire is eligible for a FY row only when asof_date <= fire_date.")
    a("")
    a("**Adjacency (R2 per RUL-2):**")
    a("- Nearest falsified relative: CN quality floors on reversal HURT (§3 F5).")
    a("  Mechanical difference: US-only, stratum (not gate), holdability horizon.")
    a("- US residual momentum falsified: this is fundamental accounting quality,")
    a("  not price momentum.")
    a("")
    a("**Quality defs:**")
    a("- Piotroski F-score: 7-point variant from fundamentals_panel columns")
    a("  (cur_assets/cur_liab absent from panel — 7 instead of 9 tests).")
    a("- Altman Z-score (approx): 4-leg proxy using equity/assets, ni/assets,")
    a("  cfo/assets, revenue/assets (NOT the canonical Altman Z — panel lacks")
    a("  cur_assets/cur_liab/retained_earnings/op_income). Cross-sectional rank only.")
    a("- Sloan accrual: (ni - cfo) / assets. Reversed for tercile: T2 = lowest")
    a("  accruals = best accounting quality. STANDALONE ONLY (no interaction arm")
    a("  per masterplan §3 F5).")
    a("")
    a("**Tercile PIT / look-ahead disclosure:**")
    a("Quality SCORES are PIT-safe (asof_date <= fire_date, assumed-120d-lag).")
    a("Tercile BOUNDARIES (q33/q67) are computed over the full calendar year of fires")
    a("(within-year cross-section), so a January fire's tercile rank uses boundaries")
    a("that include later-year fire scores. This is analysis-grade per masterplan §3 F5")
    a("('cross-sectional per fire-year') and acceptable for a holdability study.")
    a("It is NOT live-deployable: a future live chip must switch to trailing-window terciles.")
    a("")
    a("---")
    a("")
    a("## NC Yardstick (RUL-3: must appear first)")
    a("")
    a("Reference from W1_NC_REPORT.md — the bar S-QL must beat to claim value beyond")
    a("tier/freshness/proximity. Key values (deep panel, stop5 co-primary):")
    a("")
    a("| Panel | NC | Stop5 coef | 95% CI | CI excl 0? |")
    a("|---|---|---|---|---|")
    a("| deep    | NC-1A (T1-only)      | -0.0019 | [-0.016, +0.008] | no |")
    a("| deep    | NC-1B (ticks=0)      |  0.0001 | [-0.015, +0.007] | no |")
    a("| deep    | NC-2 (prox top-3ile) | -0.0427 | [-0.044, -0.031] | YES |")
    a("| baskets | NC-1A (T1-only)      | -0.0036 | [-0.011, +0.006] | no |")
    a("| baskets | NC-1B (ticks=0)      |  0.0099 | [+0.002, +0.015] | YES |")
    a("| baskets | NC-2 (prox top-3ile) | -0.1012 | [-0.108, -0.096] | YES |")
    a("")
    a("NC-2 stop5 coef is -4.3pp (deep) / -10.1pp (baskets) at top-proximity tercile.")
    a("Quality candidates must add value BEYOND proximity (marginality test via")
    a("entry_quality-band FE — DEFERRED to S-UR PR per W1 NC report).")
    a("")
    a("---")
    a("")
    a("## Trial Registration")
    a("")
    a("Family: `esx_ql_overlay` (pre-registered budget=12 at W0; amended for this run).")
    a("Pre-registered: 3 quality defs × 2 horizons × 2 forms = 12 trials.")
    a("Amendment: 63d horizon arm OMITTED (fwd_mdd_63/clean15_63 not computed in")
    a("deep-only run). Trials registered and executed: 5")
    a("  (pio_126d_standalone, pio_126d_interaction, alt_126d_standalone,")
    a("   alt_126d_interaction, slo_126d_standalone).")
    a("Interaction arms: Piotroski/Altman only; Sloan standalone only (§3 F5).")
    a("63d arm reserved for future --panel baskets run with 63d metrics added.")
    a("")
    a("---")
    a("")

    # ---- Headline numbers section ------------------------------------------
    a("## Headline Numbers (T2-vs-T0 deltas per def per panel)")
    a("")
    a("Format: pos_liftoff Δ=... [CI]; dead_money Δ=... [CI]; recall T2=%; n_T2; n_T0")
    a("Direction: pos_liftoff (+) = better; dead_money (-) = better.")
    a("CI-excl-0 = bootstrap 95% CI excludes zero. BH-rej = BH q<=0.10 rejected.")
    a("")
    for panel_name, res in all_results.items():
        if "error" in res:
            continue
        a(f"### Panel: {panel_name.upper()}")
        a("")
        for def_name in ("piotroski", "altman", "sloan"):
            dr = res.get(def_name, {})
            if "note" in dr and "effect" not in str(dr.get("holdability_effect", "")):
                a(f"- **{def_name}**: {dr.get('note', 'skipped')}")
            elif dr.get("holdability_effect"):
                hl = _headline_delta(dr)
                a(f"- **{def_name}**: {hl}")
        a("")
    a("---")
    a("")

    # ---- Per-panel study results -------------------------------------------
    for panel_name, res in all_results.items():
        a(f"## Panel: {panel_name.upper()}")
        a("")
        if "error" in res:
            a(f"**ERROR:** {res['error']}")
            a("")
            continue

        a(f"**SURVIVOR BIAS STAMP:** {res.get('survivor_stamp', '')}")
        a(f"**PIT basis:** {res.get('pit_basis', PIT_BASIS)}")
        a("")
        a(f"- Total fires loaded: {res.get('n_fires_total', 0):,}")
        a(f"- Gradable fires: {res.get('n_gradable', 0):,}")
        a(f"- FE granularity: `{res.get('fe_granularity', 'date')}` (frozen per RUL-12)")
        a("")

        # Coverage report
        cov = res.get("coverage", {})
        a("### Coverage Report")
        a("")
        a("The exclusion count below is keyed on Piotroski availability (strictest def,")
        a("requires >=2 FY rows). Fires in these tickers are excluded from the Piotroski")
        a("arm but may have Altman/Sloan coverage. See per-def coverage rows for actual")
        a("arm-level fire counts.")
        a("")
        a(f"- Fires on tickers without Piotroski-computable EDGAR history: "
          f"{cov.get('n_excluded_fires_no_edgar', '?'):,} fires "
          f"({cov.get('n_excluded_no_edgar_ticker', '?')} tickers)")
        a(f"- Piotroski coverage (gradable fires): "
          f"{cov.get('piotroski_coverage_gradable', '?'):,} / {cov.get('n_gradable', '?')}")
        a(f"- Altman coverage (gradable fires): "
          f"{cov.get('altman_coverage_gradable', '?'):,} / {cov.get('n_gradable', '?')}")
        a(f"- Sloan coverage (gradable fires): "
          f"{cov.get('sloan_coverage_gradable', '?'):,} / {cov.get('n_gradable', '?')}")
        a("")

        for def_name, def_label in [
            ("piotroski", "Piotroski F-score"),
            ("altman",    "Altman Z-score (approx)"),
            ("sloan",     "Sloan accrual (T2=low-accruals=best quality)"),
        ]:
            dr = res.get(def_name, {})
            a(f"### {def_label}")
            a("")

            if "note" in dr and not dr.get("holdability_effect"):
                a(f"**SKIPPED:** {dr.get('note', '')}")
                a(f"- n_quality_nonull: {dr.get('n_quality_nonull', 0)}")
                a("")
                continue

            a(f"Quality def: `{def_name}` | Tercile col: `{dr.get('tercile_col', '?')}`")
            a(f"n quality non-null (gradable): "
              f"{dr.get('n_top_gradable', '?')} T2, "
              f"{dr.get('n_bottom_gradable', '?')} T0")
            a(f"Recall T2 (top quality): {_fmt_pct(dr.get('recall_top'))} | "
              f"Recall T0 (bottom quality): {_fmt_pct(dr.get('recall_bottom'))}")
            a("")

            # Descriptive tercile table
            a("#### Tercile Descriptive Table (survivor bias; no controls)")
            a("")
            _write_tercile_table_md(lines, dr.get("tercile_table", []))

            # Holdability effect (primary) — patched with family-level BH
            hold = dr.get("holdability_effect", {})
            if hold.get("effects"):
                a("#### Holdability Effect (T2 vs T0, R1 FE, positional/126d primary)")
                a("")
                hold_patched = _patch_bh_panel(
                    hold, family_bh, panel_name, def_name, "standalone"
                )
                _write_effect_md(lines, hold_patched, "Holdability R1 FE Table")
            else:
                a("_No holdability effect table (insufficient rows)._")
                a("")

            # 21d context — MANDATORY BANNER
            ctx21 = dr.get("context_21d_effect", {})
            a("#### 21d Context Table")
            a("")
            a("> **ENTRY-TIMING FENCE (RUL-13):** The 21d metrics below are printed as")
            a("> CONTEXT ONLY. This lane tests HOLDABILITY, not entry timing. No entry-")
            a("> timing claims may be derived from the 21d table. Per Amendment 1 RUL-13:")
            a("> 63d/126d are the only endpoints that decide an S-QL verdict.")
            a("")
            if ctx21.get("effects"):
                _write_effect_md(lines, ctx21, "21d Context R1 FE Table (CONTEXT ONLY)")
            else:
                a("_No 21d context table (insufficient rows)._")
                a("")

            # Era table
            era_recs = dr.get("era_table", [])
            if era_recs:
                era_df = pd.DataFrame(era_recs)
                prog = era_df[era_df["era"].isin(PROGRAM_ERAS)] if "era" in era_df.columns else era_df
                if not prog.empty:
                    a("#### Era × Tercile Table (program eras)")
                    a("")
                    cols = [c for c in ["era", "tercile", "n_fires", "stop5_rate", "pos_liftoff", "dead_money"]
                            if c in prog.columns]
                    a("| " + " | ".join(cols) + " |")
                    a("|" + "---|" * len(cols))
                    for _, row in prog.iterrows():
                        cells = []
                        for c in cols:
                            v = row.get(c)
                            if v is None:
                                cells.append("—")
                            elif c in ("stop5_rate", "pos_liftoff", "dead_money"):
                                cells.append(_fmt_pct(v))
                            elif c == "tercile":
                                cells.append(str(int(v)))
                            else:
                                cells.append(str(v) if v is not None else "—")
                        a("| " + " | ".join(cells) + " |")
                    a("")

            # Interaction arm
            ia = dr.get("interaction_arm", {})
            if ia.get("note"):
                a(f"**Interaction arm:** {ia['note']}")
                a("")
            elif ia.get("effects"):
                a("#### Interaction Arm: Quality T2 × Washout T2 vs rest")
                a("")
                a("Stratum = 1 iff quality tercile = 2 (top) AND washout depth tercile = 2 (deep).")
                a("Tests whether the quality holdability premium concentrates in deep-washout fires.")
                a("")
                ia_patched = _patch_bh_panel(
                    ia, family_bh, panel_name, def_name, "interaction"
                )
                _write_effect_md(lines, ia_patched, "Interaction R1 FE Table")
            elif ia.get("note") and "excluded" not in str(ia.get("note", "")):
                a(f"**Interaction arm:** {ia.get('note', 'n/a')}")
                a("")

        a("---")
        a("")

    # ---- BH summary across family -----------------------------------------
    a("## BH FDR Summary (esx_ql_overlay family)")
    a("")
    a("BH q<=0.10 applied within the esx_ql_overlay family.")
    a("All holdability p-values (standalone + interaction arms) pooled for the family-level BH.")
    a("Per masterplan §5: BH q<=0.10 applies per family across ALL pre-registered forms.")
    a("The per-arm 'BH rej?' columns above are driven by this family-level panel.")
    a("")

    all_pvals: list[tuple[str, float | None]] = []
    for panel_name, res in all_results.items():
        if "error" in res:
            continue
        for def_name in ("piotroski", "altman", "sloan"):
            dr = res.get(def_name, {})
            # Standalone arm holdability
            hold = dr.get("holdability_effect", {})
            for e in hold.get("effects", []):
                label = f"{panel_name}/{def_name}/standalone/{e.get('label','?')}"
                all_pvals.append((label, e.get("p_value")))
            # Interaction arm holdability (Piotroski/Altman only)
            ia = dr.get("interaction_arm", {})
            if ia.get("effects"):
                for e in ia.get("effects", []):
                    label = f"{panel_name}/{def_name}/interaction/{e.get('label','?')}"
                    all_pvals.append((label, e.get("p_value")))

    if all_pvals:
        labels_bh  = [x[0] for x in all_pvals]
        pvals_bh   = [x[1] for x in all_pvals]
        bh_results = bh_correction(pvals_bh, labels_bh)
        rej_count  = sum(1 for b in bh_results if b.get("rejected"))
        a(f"Total holdability tests (standalone + interaction): {len(all_pvals)} | "
          f"BH rejections (q<=0.10): {rej_count}")
        a("")
        a("| Test | p-value | q-value | BH rej? |")
        a("|---|---|---|---|")
        for b in bh_results:
            rej_str = "YES" if b.get("rejected") else "no" if b.get("rejected") is not None else "—"
            a(f"| {b['label']} | {_fmt_f(b.get('p_value'), 4)} | "
              f"{_fmt_f(b.get('q_value'), 4)} | {rej_str} |")
        a("")

    a("---")
    a("")
    a("## Null results declaration (mandatory per masterplan §5)")
    a("")
    a("Any outcome with CI-including-0 is a NULL result. Nulls are printed here,")
    a("not hidden. A null means the quality tercile does NOT show distinguishable")
    a("holdability improvement (beyond tier/date noise) at this sample size.")
    a("")
    a("**S-QL verdict: BLOCKED** — this deep-only run cannot satisfy the §3 F5")
    a("dev/holdout-replication requirement ('tercile spread replicated in sign on")
    a("dev/holdout'). No S-QL verdict is drawn from this report. A final verdict")
    a("requires the baskets panel dev/holdout split run:")
    a("`python scripts/research/run_w2_sql.py --panel baskets`")
    a("")
    a("*No promotion language. The word 'validated' is deliberately absent.*")
    a("*Studies only. No product change from this PR.*")
    a("")
    a("---")
    a("")
    a("*Generated by `scripts/research/run_w2_sql.py`*")
    a("*Grader: engine/grading.py (program barriers, RUL-9).*")
    a("*PIT basis: assumed-120d-lag (fundamentals_panel asof_date = period_end+120d flat).*")
    a("*Horizon doctrine: RUL-13 — 63d/126d = holdability lane; 21d printed as context only.*")
    a("*R1 estimator: date-FE OLS + block-bootstrap 95% CI (RUL-12).*")
    a("*BH q<=0.10 within esx_ql_overlay family.*")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s (%d lines)", out_path, len(lines))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Entry-Stack Expansion W2 — S-QL Quality Holdability Overlay.",
    )
    parser.add_argument(
        "--out", default=str(_RESEARCH_DIR / "W2_SQL_REPORT.md"),
        help="Output path for W2_SQL_REPORT.md",
    )
    parser.add_argument(
        "--n-bootstrap", type=int, default=1000,
        help="Block-bootstrap resamples (default 1000; use --smoke for 50)",
    )
    parser.add_argument(
        "--panel", nargs="+", choices=["deep", "baskets"],
        default=None,
        help="Restrict to named panel(s); default runs all.",
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Quick smoke test: 50 bootstrap, deep panel only.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    n_boot = 50 if args.smoke else args.n_bootstrap
    panels = ["deep"] if args.smoke else args.panel

    log.info("Starting W2 S-QL study (n_bootstrap=%d, panels=%s)", n_boot, panels or "all")
    all_results = run_all_panels(n_bootstrap=n_boot, panels=panels)
    write_report(all_results, Path(args.out))
    log.info("Done. Report at %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
