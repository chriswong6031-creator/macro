"""
MRI PR-E: Release Playbook v1 — Descriptive Transmission Study

DESCRIPTIVE ONLY (MRI-R1/R2/R3): no signal, no gate, no entry/exit claim;
announcement-premium and scored-surprise kills stand.

Reads:
  data/fred_vintage/vintages.parquet      — CPIAUCSL, PAYEMS initial prints
  data/fred/DGS10.parquet                 — 10y yield (us10y, bp)
  data/fred/T10Y2Y.parquet                — 2s10s spread (spread_2s10s, bp)
  data/fred/DTWEXBGS.parquet              — broad dollar (broad_dollar, index)
  data/yahoo/SPY.parquet                  — SPY close (close)
  data/regime/regime_history.parquet      — quad label (revision_optimistic)

Writes:
  research/release_playbook/results/playbook_v1.json
  research/release_playbook/results/RESULTS_PLAYBOOK_V1.md
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Bootstrap parameters (house convention)
BOOT_DRAWS = 800
BOOT_SEED = 7

# Minimum events to report a cell
MIN_N = 8

# Surprise warm-up (need 24 prior events for sigma)
WARMUP = 24

# Bucket thresholds (frozen)
HOT_THRESH = 0.5
COLD_THRESH = -0.5

# COVID exclusion window (period months, inclusive)
COVID_START = pd.Timestamp("2020-03-01")
COVID_END = pd.Timestamp("2020-06-30")

# Era definitions: {era_key: (start, end)} inclusive on period month
ERA_CPI = {
    "pre2010": (pd.Timestamp("1997-01-01"), pd.Timestamp("2009-12-31")),
    "2010_2020": (pd.Timestamp("2010-01-01"), pd.Timestamp("2020-02-29")),
    "2021plus": (pd.Timestamp("2021-01-01"), pd.Timestamp("2099-12-31")),
}
ERA_NFP = {
    "2010_2020": (pd.Timestamp("2010-01-01"), pd.Timestamp("2020-02-29")),
    "2021plus": (pd.Timestamp("2021-01-01"), pd.Timestamp("2099-12-31")),
}

# Horizons to compute
HORIZONS = ["h0", "h1", "h5", "h21"]
HORIZON_N = {"h0": 0, "h1": 1, "h5": 5, "h21": 21}

OUTCOMES = ["dgs10_bp", "t10y2y_bp", "dollar_pct", "spy_pct"]


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_vintages() -> pd.DataFrame:
    path = REPO_ROOT / "data" / "fred_vintage" / "vintages.parquet"
    df = pd.read_parquet(path)
    df["period"] = pd.to_datetime(df["period"])
    df["realtime_start"] = pd.to_datetime(df["realtime_start"])
    return df


def load_market_series() -> dict[str, pd.Series]:
    """Returns dict of series keyed by outcome name, indexed by date."""
    out: dict[str, pd.Series] = {}

    # DGS10 — unit is pct (e.g. 4.06), convert to bp by ×100
    dgs10 = pd.read_parquet(REPO_ROOT / "data" / "fred" / "DGS10.parquet")
    dgs10.index = pd.to_datetime(dgs10.index)
    out["dgs10_raw"] = dgs10["us10y"] * 100  # now in bp (× 100 from pct)

    # T10Y2Y — same unit treatment
    t10 = pd.read_parquet(REPO_ROOT / "data" / "fred" / "T10Y2Y.parquet")
    t10.index = pd.to_datetime(t10.index)
    out["t10y2y_raw"] = t10["spread_2s10s"] * 100

    # DTWEXBGS — index level, outcome = pct change
    dtwex = pd.read_parquet(REPO_ROOT / "data" / "fred" / "DTWEXBGS.parquet")
    dtwex.index = pd.to_datetime(dtwex.index)
    out["dollar_raw"] = dtwex["broad_dollar"]

    # SPY — use 'close' column for adjusted price
    spy = pd.read_parquet(REPO_ROOT / "data" / "yahoo" / "SPY.parquet")
    spy.index = pd.to_datetime(spy.index)
    # MultiIndex column may be present — flatten if needed
    if hasattr(spy.columns, "levels"):
        spy.columns = spy.columns.get_level_values(0)
    out["spy_raw"] = spy["close"]

    return out


def load_regime() -> pd.Series:
    path = REPO_ROOT / "data" / "regime" / "regime_history.parquet"
    reg = pd.read_parquet(path)
    reg.index = pd.to_datetime(reg.index)
    return reg["quad"]


# ---------------------------------------------------------------------------
# Initial prints extraction
# ---------------------------------------------------------------------------

def extract_initial_prints(vintages: pd.DataFrame, series: str) -> pd.DataFrame:
    """Return one row per period: earliest realtime_start = initial print."""
    df = vintages[vintages["series"] == series].copy()
    # Sort by period then realtime_start; keep first ROW per period.
    # head(1) rather than .first(): pandas GroupBy.first() skips NaN per
    # column, which would silently substitute a later (revised) vintage's
    # value if the earliest vintage were NaN — a PIT violation.
    df = df.sort_values(["period", "realtime_start"])
    df = df.groupby("period", as_index=False).head(1)
    df = df[["period", "value", "realtime_start"]].copy()
    df = df.rename(columns={"value": "initial_value", "realtime_start": "release_date"})
    df = df.sort_values("period").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Surprise construction (PIT)
# ---------------------------------------------------------------------------

def compute_mom(df: pd.DataFrame) -> pd.DataFrame:
    """Compute MoM change using initial-vintage values."""
    df = df.copy().reset_index(drop=True)
    df["mom"] = df["initial_value"].diff()  # value[t] - value[t-1]
    return df


def compute_surprises(df: pd.DataFrame) -> pd.DataFrame:
    """Add naive_prior, realized_surprise, trailing_sigma, std_surprise."""
    df = df.copy().reset_index(drop=True)
    df["naive_prior"] = df["mom"].shift(1)
    df["realized_surprise"] = df["mom"] - df["naive_prior"]

    # Expanding-window sigma over prior 24 events (PIT: excludes current)
    sigmas = []
    for i in range(len(df)):
        if i < WARMUP:
            sigmas.append(np.nan)
        else:
            window = df["realized_surprise"].iloc[i - WARMUP: i].values
            sigmas.append(float(np.std(window, ddof=1)) if len(window) >= 2 else np.nan)
    df["trailing_sigma"] = sigmas

    df["std_surprise"] = df["realized_surprise"] / df["trailing_sigma"]
    return df


def assign_bucket(s: float) -> str | None:
    if np.isnan(s):
        return None
    if s > HOT_THRESH:
        return "hot"
    if s < COLD_THRESH:
        return "cold"
    return "inline"


# ---------------------------------------------------------------------------
# Trading-day alignment
# ---------------------------------------------------------------------------

def align_to_trading_day(date: pd.Timestamp, trading_days: pd.DatetimeIndex) -> pd.Timestamp | None:
    """Return date if it's a trading day, else next available trading day."""
    if date in trading_days:
        return date
    future = trading_days[trading_days > date]
    if len(future) == 0:
        return None
    return future[0]


def get_session_close(
    base_date: pd.Timestamp,
    n_sessions: int,
    trading_days: pd.DatetimeIndex,
) -> pd.Timestamp | None:
    """Return trading day that is n_sessions after base_date in trading_days."""
    if base_date not in trading_days:
        return None
    idx = trading_days.get_loc(base_date)
    target_idx = idx + n_sessions
    if target_idx < 0 or target_idx >= len(trading_days):
        return None
    return trading_days[target_idx]


# ---------------------------------------------------------------------------
# Outcome computation
# ---------------------------------------------------------------------------

def compute_outcomes_for_event(
    release_date: pd.Timestamp,
    mkt: dict[str, pd.Series],
    trading_days: pd.DatetimeIndex,
) -> dict[str, dict[str, float | None]]:
    """Compute h0/h1/h5/h21 outcomes for each market variable."""
    # Align release date to nearest following trading day
    event_day = align_to_trading_day(release_date, trading_days)
    if event_day is None:
        return {h: {o: None for o in OUTCOMES} for h in HORIZONS}

    # Prior close = one session before event_day
    idx = trading_days.get_loc(event_day)
    if idx == 0:
        return {h: {o: None for o in OUTCOMES} for h in HORIZONS}
    prior_day = trading_days[idx - 1]

    results: dict[str, dict[str, float | None]] = {}
    for hz in HORIZONS:
        n = HORIZON_N[hz]
        if n == 0:
            target_day = event_day
        else:
            target_idx = idx + n
            if target_idx >= len(trading_days):
                results[hz] = {o: None for o in OUTCOMES}
                continue
            target_day = trading_days[target_idx]

        row: dict[str, float | None] = {}
        # DGS10 in bp change
        dgs10 = mkt["dgs10_raw"]
        if prior_day in dgs10.index and target_day in dgs10.index:
            p0 = dgs10.loc[prior_day]
            p1 = dgs10.loc[target_day]
            row["dgs10_bp"] = float(p1 - p0) if pd.notna(p0) and pd.notna(p1) else None
        else:
            row["dgs10_bp"] = None

        # T10Y2Y in bp change
        t10 = mkt["t10y2y_raw"]
        if prior_day in t10.index and target_day in t10.index:
            p0 = t10.loc[prior_day]
            p1 = t10.loc[target_day]
            row["t10y2y_bp"] = float(p1 - p0) if pd.notna(p0) and pd.notna(p1) else None
        else:
            row["t10y2y_bp"] = None

        # Dollar pct change
        dtwex = mkt["dollar_raw"]
        if prior_day in dtwex.index and target_day in dtwex.index:
            p0 = dtwex.loc[prior_day]
            p1 = dtwex.loc[target_day]
            row["dollar_pct"] = float((p1 / p0 - 1) * 100) if pd.notna(p0) and pd.notna(p1) and p0 != 0 else None
        else:
            row["dollar_pct"] = None

        # SPY pct return
        spy = mkt["spy_raw"]
        if prior_day in spy.index and target_day in spy.index:
            p0 = spy.loc[prior_day]
            p1 = spy.loc[target_day]
            row["spy_pct"] = float((p1 / p0 - 1) * 100) if pd.notna(p0) and pd.notna(p1) and p0 != 0 else None
        else:
            row["spy_pct"] = None

        results[hz] = row
    return results


# ---------------------------------------------------------------------------
# Bootstrap CI (pure numpy)
# ---------------------------------------------------------------------------

def bootstrap_ci(
    values: np.ndarray,
    n_draws: int = BOOT_DRAWS,
    seed: int = BOOT_SEED,
    ci: float = 0.95,
) -> tuple[float, float]:
    """Event-level bootstrap CI for the mean."""
    rng = np.random.default_rng(seed)
    n = len(values)
    if n == 0:
        return (np.nan, np.nan)
    if n == 1:
        return (float(values[0]), float(values[0]))
    boot_means = np.empty(n_draws)
    for i in range(n_draws):
        sample = rng.choice(values, size=n, replace=True)
        boot_means[i] = np.mean(sample)
    alpha = (1 - ci) / 2
    lo = float(np.percentile(boot_means, alpha * 100))
    hi = float(np.percentile(boot_means, (1 - alpha) * 100))
    return (lo, hi)


# ---------------------------------------------------------------------------
# Cell aggregation
# ---------------------------------------------------------------------------

def aggregate_cells(
    events: pd.DataFrame,  # columns: release_date, period, bucket, std_surprise, covid_flag, era, quad, + outcome cols
    outcomes: list[str],
    eras: dict[str, tuple[pd.Timestamp, pd.Timestamp]],
    release_name: str,
) -> list[dict]:
    """Produce records for all (bucket, outcome, horizon, era, regime) cells."""
    records = []
    buckets = ["hot", "inline", "cold"]

    # Base events (non-covid)
    base = events[~events["covid_flag"]].copy()

    # Full dataset (all eras combined)
    all_eras: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = dict(eras)
    all_eras["all"] = (pd.Timestamp("1990-01-01"), pd.Timestamp("2099-12-31"))

    for era_key, (era_start, era_end) in all_eras.items():
        era_mask = (base["period"] >= era_start) & (base["period"] <= era_end)
        era_df = base[era_mask].copy()

        for bucket in buckets:
            bdf = era_df[era_df["bucket"] == bucket].copy()

            for outcome in outcomes:
                for hz in HORIZONS:
                    col = f"{outcome}_{hz}"
                    if col not in bdf.columns:
                        continue
                    vals = bdf[col].dropna().values.astype(float)
                    n = len(vals)

                    if n < MIN_N:
                        continue

                    mean_v = float(np.mean(vals))
                    median_v = float(np.median(vals))
                    ci_lo, ci_hi = bootstrap_ci(vals)

                    records.append({
                        "release": release_name,
                        "bucket": bucket,
                        "outcome": outcome,
                        "horizon": hz,
                        "era": era_key,
                        "regime": None,
                        "n": n,
                        "mean": round(mean_v, 4),
                        "median": round(median_v, 4),
                        "ci_lo": round(ci_lo, 4),
                        "ci_hi": round(ci_hi, 4),
                    })

    # Regime-conditioned cells (revision_optimistic; all eras, no era split)
    if "quad" in events.columns:
        for quad_val in ["Q1", "Q2", "Q3", "Q4"]:
            rdf = base[base["quad"] == quad_val].copy()
            for bucket in buckets:
                bdf = rdf[rdf["bucket"] == bucket].copy()
                for outcome in outcomes:
                    for hz in HORIZONS:
                        col = f"{outcome}_{hz}"
                        if col not in bdf.columns:
                            continue
                        vals = bdf[col].dropna().values.astype(float)
                        n = len(vals)
                        if n < MIN_N:
                            continue
                        mean_v = float(np.mean(vals))
                        median_v = float(np.median(vals))
                        ci_lo, ci_hi = bootstrap_ci(vals)
                        records.append({
                            "release": release_name,
                            "bucket": bucket,
                            "outcome": outcome,
                            "horizon": hz,
                            "era": "all",
                            "regime": quad_val,
                            "n": n,
                            "mean": round(mean_v, 4),
                            "median": round(median_v, 4),
                            "ci_lo": round(ci_lo, 4),
                            "ci_hi": round(ci_hi, 4),
                        })

    return records


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def build_events(
    series_name: str,
    release_name: str,
    period_start: pd.Timestamp,
    mkt: dict[str, pd.Series],
    trading_days: pd.DatetimeIndex,
    regime_quad: pd.Series,
    vintages: pd.DataFrame,
) -> pd.DataFrame:
    """Extract events, compute surprises, outcomes, flags."""
    prints = extract_initial_prints(vintages, series_name)
    # Filter to period_start floor
    prints = prints[prints["period"] >= period_start].copy()
    prints = compute_mom(prints)
    prints = compute_surprises(prints)

    # Bucket assignment
    prints["bucket"] = prints["std_surprise"].apply(assign_bucket)

    # COVID flag
    prints["covid_flag"] = (prints["period"] >= COVID_START) & (prints["period"] <= COVID_END)

    # Regime label (revision_optimistic): align release_date to regime index
    def get_quad(release_date: pd.Timestamp) -> str | None:
        aligned = align_to_trading_day(release_date, trading_days)
        if aligned is None:
            return None
        if aligned in regime_quad.index:
            val = regime_quad.loc[aligned]
            return val if pd.notna(val) else None
        return None

    prints["quad"] = prints["release_date"].apply(get_quad)

    # Compute all outcomes
    for outcome in OUTCOMES:
        for hz in HORIZONS:
            prints[f"{outcome}_{hz}"] = None

    for i, row in prints.iterrows():
        if pd.isna(row["bucket"]):
            continue
        oz = compute_outcomes_for_event(row["release_date"], mkt, trading_days)
        for hz in HORIZONS:
            for outcome in OUTCOMES:
                val = oz.get(hz, {}).get(outcome)
                prints.at[i, f"{outcome}_{hz}"] = val

    return prints


def run() -> None:
    print("Loading data...")
    vintages = load_vintages()
    mkt = load_market_series()
    regime_quad = load_regime()

    # Build unified trading-day index from SPY closes
    trading_days = mkt["spy_raw"].dropna().index.sort_values()

    # ---------------------------------------------------------------------------
    # CPI events
    # ---------------------------------------------------------------------------
    print("Building CPI events...")
    cpi_events = build_events(
        series_name="CPIAUCSL",
        release_name="cpi",
        period_start=pd.Timestamp("1997-01-01"),
        mkt=mkt,
        trading_days=trading_days,
        regime_quad=regime_quad,
        vintages=vintages,
    )

    # ---------------------------------------------------------------------------
    # NFP events
    # ---------------------------------------------------------------------------
    print("Building NFP events...")
    nfp_events = build_events(
        series_name="PAYEMS",
        release_name="nfp",
        period_start=pd.Timestamp("2010-01-01"),
        mkt=mkt,
        trading_days=trading_days,
        regime_quad=regime_quad,
        vintages=vintages,
    )

    # ---------------------------------------------------------------------------
    # Aggregate cells
    # ---------------------------------------------------------------------------
    print("Aggregating cells...")
    cpi_records = aggregate_cells(cpi_events, OUTCOMES, ERA_CPI, "cpi")
    nfp_records = aggregate_cells(nfp_events, OUTCOMES, ERA_NFP, "nfp")
    all_records = cpi_records + nfp_records

    # ---------------------------------------------------------------------------
    # Write JSON
    # ---------------------------------------------------------------------------
    json_path = OUT_DIR / "playbook_v1.json"
    with open(json_path, "w") as f:
        json.dump(all_records, f, indent=2, default=str)
    print(f"Written: {json_path} ({len(all_records)} cells)")

    # ---------------------------------------------------------------------------
    # Write markdown results
    # ---------------------------------------------------------------------------
    md_path = OUT_DIR / "RESULTS_PLAYBOOK_V1.md"
    write_results_md(md_path, all_records, cpi_events, nfp_events)
    print(f"Written: {md_path}")


# ---------------------------------------------------------------------------
# Results markdown writer
# ---------------------------------------------------------------------------

def write_results_md(
    path: Path,
    all_records: list[dict],
    cpi_events: pd.DataFrame,
    nfp_events: pd.DataFrame,
) -> None:
    lines: list[str] = []

    lines.append("# Release Playbook v1 — Descriptive Transmission Study")
    lines.append("")
    lines.append("> **DESCRIPTIVE ONLY (MRI-R1/R2/R3): no signal, no gate, no entry/exit claim;")
    lines.append("> announcement-premium and scored-surprise kills stand.**")
    lines.append(">")
    lines.append("> Regime labels (quad) are latest-revised, NOT point-in-time (labeled revision_optimistic).")
    lines.append(">")
    lines.append("> Overlap caveat: h21 windows for adjacent monthly events may overlap by ~0-5")
    lines.append("> trading days. No correction applied in v1.")
    lines.append(">")
    lines.append("> Era reconciliation: the `all` era covers every non-COVID event, INCLUDING")
    lines.append("> the 2020-07..12 recovery months that belong to no named era cell — so the")
    lines.append("> named-era rows do not sum to `all` (gap: 6 events per release type).")
    lines.append("")

    # --- Event counts summary ---
    lines.append("## Event Summary")
    lines.append("")
    lines.append("### CPI (CPIAUCSL) Event Counts")
    lines.append("")
    _add_event_count_table(lines, cpi_events, ERA_CPI, "cpi")

    lines.append("")
    lines.append("### NFP (PAYEMS) Event Counts")
    lines.append("")
    _add_event_count_table(lines, nfp_events, ERA_NFP, "nfp")

    # --- COVID disrupted prints ---
    lines.append("")
    lines.append("## COVID-Disrupted Prints (Excluded from Bucket Stats)")
    lines.append("")
    _add_covid_table(lines, cpi_events, "CPI")
    _add_covid_table(lines, nfp_events, "NFP")

    # --- Main result tables ---
    for release_name, release_label in [("cpi", "CPI"), ("nfp", "NFP")]:
        eras = ERA_CPI if release_name == "cpi" else ERA_NFP
        lines.append("")
        lines.append(f"## {release_label} Results by Era and Outcome")
        lines.append("")
        for era_key in list(eras.keys()) + ["all"]:
            lines.append(f"### {release_label} — Era: {era_key}")
            lines.append("")
            for outcome, outcome_label, unit in [
                ("dgs10_bp", "DGS10", "bp"),
                ("t10y2y_bp", "T10Y2Y (2s10s)", "bp"),
                ("dollar_pct", "Broad Dollar (DTWEXBGS)", "%"),
                ("spy_pct", "SPY", "%"),
            ]:
                lines.append(f"#### {outcome_label} ({unit})")
                lines.append("")
                _add_bucket_table(lines, all_records, release_name, outcome, era_key, regime=None)
                lines.append("")

    # --- Regime-conditioned cells ---
    lines.append("")
    lines.append("## Regime-Conditioned Cells (revision_optimistic; n≥8 only)")
    lines.append("")
    lines.append("Regime labels are latest-revised quad values — NOT point-in-time.")
    lines.append("")
    for release_name, release_label in [("cpi", "CPI"), ("nfp", "NFP")]:
        for quad_val in ["Q1", "Q2", "Q3", "Q4"]:
            quad_records = [
                r for r in all_records
                if r["release"] == release_name and r["regime"] == quad_val
            ]
            if not quad_records:
                continue
            lines.append(f"### {release_label} in {quad_val}")
            lines.append("")
            for outcome, outcome_label, unit in [
                ("dgs10_bp", "DGS10", "bp"),
                ("spy_pct", "SPY", "%"),
            ]:
                lines.append(f"#### {outcome_label} ({unit})")
                lines.append("")
                _add_bucket_table(lines, all_records, release_name, outcome, "all", regime=quad_val)
                lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _add_event_count_table(
    lines: list[str],
    events: pd.DataFrame,
    eras: dict,
    release_name: str,
) -> None:
    base = events[~events["covid_flag"] & events["bucket"].notna()]
    lines.append("| Era | Hot | Inline | Cold | Total |")
    lines.append("|---|---|---|---|---|")
    for era_key, (era_start, era_end) in eras.items():
        era_df = base[(base["period"] >= era_start) & (base["period"] <= era_end)]
        hot = (era_df["bucket"] == "hot").sum()
        inline = (era_df["bucket"] == "inline").sum()
        cold = (era_df["bucket"] == "cold").sum()
        total = len(era_df)
        lines.append(f"| {era_key} | {hot} | {inline} | {cold} | {total} |")
    # All
    all_df = base
    hot = (all_df["bucket"] == "hot").sum()
    inline = (all_df["bucket"] == "inline").sum()
    cold = (all_df["bucket"] == "cold").sum()
    total = len(all_df)
    lines.append(f"| all | {hot} | {inline} | {cold} | {total} |")


def _add_covid_table(lines: list[str], events: pd.DataFrame, label: str) -> None:
    covid = events[events["covid_flag"]].copy()
    if len(covid) == 0:
        lines.append(f"No {label} COVID-disrupted events in range.")
        return
    lines.append(f"**{label} COVID events:**")
    lines.append("")
    lines.append("| Period | Release Date | MoM | Std Surprise |")
    lines.append("|---|---|---|---|")
    for _, row in covid.iterrows():
        period = row["period"].strftime("%Y-%m") if pd.notna(row["period"]) else "N/A"
        rdate = row["release_date"].strftime("%Y-%m-%d") if pd.notna(row["release_date"]) else "N/A"
        mom = f"{row['mom']:.3f}" if pd.notna(row.get("mom")) else "N/A"
        std = f"{row['std_surprise']:.2f}" if pd.notna(row.get("std_surprise")) else "N/A (warm-up)"
        lines.append(f"| {period} | {rdate} | {mom} | {std} |")
    lines.append("")


def _fmt(v: float | None, decimals: int = 2) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{decimals}f}"


def _add_bucket_table(
    lines: list[str],
    records: list[dict],
    release_name: str,
    outcome: str,
    era: str,
    regime: str | None,
) -> None:
    headers = ["Bucket", "h0 n", "h0 mean", "h0 CI", "h1 n", "h1 mean", "h1 CI",
               "h5 n", "h5 mean", "h5 CI", "h21 n", "h21 mean", "h21 CI"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")

    for bucket in ["hot", "inline", "cold"]:
        row_parts = [bucket]
        for hz in HORIZONS:
            match = [
                r for r in records
                if r["release"] == release_name
                and r["bucket"] == bucket
                and r["outcome"] == outcome
                and r["horizon"] == hz
                and r["era"] == era
                and r["regime"] == regime
            ]
            if match:
                r = match[0]
                n = r["n"]
                mean_v = _fmt(r["mean"])
                ci = f"[{_fmt(r['ci_lo'])}, {_fmt(r['ci_hi'])}]"
                row_parts += [str(n), mean_v, ci]
            else:
                row_parts += ["<8", "—", "—"]
        lines.append("| " + " | ".join(row_parts) + " |")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run()
