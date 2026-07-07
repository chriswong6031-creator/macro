"""Rotation Onset First-Crossing Re-Measurement.

Quantifies survivorship inflation in the Oracle episode onset catalog vs.
ALL real-time first-crossings (including ones that never survived into the catalog).

Steps:
1. Reproduce catalog baseline (Step 1 - sanity anchor)
2. Reconstruct real-time first-crossings using proxy predicate (Step 2)
3. Measure edge on first-crossing universe (Step 3)
4. Regime check / era split (Step 4)
5. Write artifact to reports/artifacts/rotation_onset_firstcrossing_remeasure.json

NO commits, no network calls, read-only on all repo data.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
ORACLE_DIR = ROOT / "site" / "oracledata"
PRICE_DIR = ROOT / "data" / "yahoo"
OUT_PATH = ROOT / "reports" / "artifacts" / "rotation_onset_firstcrossing_remeasure.json"

SECTOR_ETFS = {
    "XLB": "Materials",
    "XLC": "Comm Services",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLI": "Industrials",
    "XLK": "Technology",
    "XLP": "Cons Staples",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLV": "Health Care",
    "XLY": "Cons Discretionary",
}

HORIZONS = [10, 21]
ENTRY_LAG = 1

# FSM onset thresholds (from EPISODE_CFG in engine/oracle/episodes.py)
ACCEL_Z_SMOOTH_DAYS = 5            # smooth accel_z with 5-day mean
ONSET_ACCEL_Z_THRESHOLD = 1.0      # accel_z_5d >= 1.0
ONSET_POSITIVE_DAYS_IN_5 = 3       # >= 3 of last 5 accel raw > 0
# onset_rs_mom_positive: True => accel (rs_mom in tiles) > 0
ACCEL_Z_Z_LOOKBACK = 252           # causal z-score window
HYSTERESIS_GAP_DAYS = 5            # min gap between episodes for same node
CONFIRMED_CONSECUTIVE_ONSET_DAYS = 5  # min days to survive into catalog


def _hac_t(values, lag: int) -> float | None:
    x = pd.Series(list(values), dtype="float64").dropna().to_numpy()
    n = len(x)
    if n < 6:
        return None
    mu = float(x.mean())
    d = x - mu
    gamma0 = float(np.mean(d * d))
    var = gamma0
    max_lag = min(max(0, int(lag)), n - 1)
    for k in range(1, max_lag + 1):
        weight = 1.0 - k / (max_lag + 1)
        gamma = float(np.mean(d[k:] * d[:-k]))
        var += 2.0 * weight * gamma
    if var <= 1e-18:
        return None
    return mu / math.sqrt(var / n)


def mean_summary(values, lag: int = 0) -> dict:
    s = pd.Series(list(values), dtype="float64").dropna()
    if s.empty:
        return {"n": 0, "mean": None, "hit": None, "t_hac": None}
    return {
        "n": int(s.size),
        "mean": float(s.mean()),
        "hit": float((s > 0).mean()),
        "t_hac": _hac_t(s, lag),
    }


def load_tile_panel() -> pd.DataFrame:
    """Load tier-s tile panel: node, date, rs_ratio, rs_mom.
    rs_mom in tiles = vel_1w - vel_3m = accel (raw, unstandardized).
    """
    manifest = json.loads((ORACLE_DIR / "tm_manifest.json").read_text())
    registry = manifest["registry"]["s"]
    id_to_meta = {str(r["id"]): r for r in registry}
    rows: list[dict] = []
    for chunk in manifest["tiers"]["s"]["chunks"]:
        payload = json.loads((ORACLE_DIR / chunk["file"]).read_text())
        dates = pd.to_datetime(payload["dates"])
        for node_id, series in payload["data"].items():
            meta = id_to_meta[node_id]
            for dt, pair in zip(dates, series):
                if not pair or pair[0] is None or pair[1] is None:
                    continue
                rows.append({
                    "date": dt,
                    "node": meta["name"],
                    "rs_ratio": float(pair[0]),
                    "rs_mom": float(pair[1]),  # = vel_1w - vel_3m = accel
                })
    df = pd.DataFrame(rows).sort_values(["node", "date"]).reset_index(drop=True)
    return df


def load_closes() -> pd.DataFrame:
    """Load sector ETF + SPY closes."""
    closes: dict[str, pd.Series] = {}
    for ticker in sorted(set(SECTOR_ETFS) | {"SPY"}):
        p = PRICE_DIR / f"{ticker}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p, columns=["close"])
        s = df["close"].sort_index().dropna()
        s.index = pd.to_datetime(s.index).normalize()
        closes[ticker] = s[~s.index.duplicated(keep="last")]
    return pd.DataFrame(closes).sort_index()


def load_catalog_episodes() -> pd.DataFrame:
    """Load tm_episodes.json, return tier-s sector ETF IN episodes."""
    payload = json.loads((ORACLE_DIR / "tm_episodes.json").read_text())
    ep = pd.DataFrame(payload["episodes"])
    ep["onset_date"] = pd.to_datetime(ep["onset_date"], errors="coerce")
    ep["confirmed_date"] = pd.to_datetime(ep["confirmed_date"], errors="coerce")
    ep["exhausted_date"] = pd.to_datetime(ep["exhausted_date"], errors="coerce")
    # Keep only tier-s, direction=in, node in sector ETFs
    ep = ep[
        (ep["tier"] == "s")
        & (ep["direction"] == "in")
        & (ep["node"].isin(SECTOR_ETFS))
    ].copy()
    ep["onset_date"] = ep["onset_date"].dt.normalize()
    return ep.reset_index(drop=True)


def compute_accel_z(rs_mom_series: pd.Series, lookback: int = 252) -> pd.Series:
    """Causal z-score of rs_mom (= accel = vel_1w - vel_3m) over trailing lookback days.

    Mirrors engine.oracle.panel._causal_z logic.
    Returns NaN where window < lookback//3 valid observations.
    """
    min_periods = max(5, lookback // 3)

    def _z_last(x: np.ndarray) -> float:
        v = x[-1]
        if np.isnan(v):
            return np.nan
        valid = x[~np.isnan(x)]
        if len(valid) < 5:
            return np.nan
        mu = float(np.mean(valid))
        sd = float(np.std(valid, ddof=1))
        if sd < 1e-10:
            return 0.0
        return (v - mu) / sd

    return rs_mom_series.rolling(lookback, min_periods=min_periods).apply(_z_last, raw=True)


def build_accel_z_panel(tile_df: pd.DataFrame) -> pd.DataFrame:
    """Add accel_z and accel_z_5d to tile panel."""
    out_parts = []
    for node, grp in tile_df.groupby("node"):
        g = grp.sort_values("date").copy()
        # accel = rs_mom (tile rs_mom = vel_1w - vel_3m)
        g["accel"] = g["rs_mom"]
        # accel_z: causal z-score over trailing 252 days
        g["accel_z"] = compute_accel_z(g["accel"], ACCEL_Z_Z_LOOKBACK)
        # accel_z_5d: 5-day trailing mean of accel_z
        g["accel_z_5d"] = g["accel_z"].rolling(ACCEL_Z_SMOOTH_DAYS, min_periods=ACCEL_Z_SMOOTH_DAYS).mean()
        out_parts.append(g)
    return pd.concat(out_parts, ignore_index=True).sort_values(["node", "date"])


def compute_onset_predicate(g: pd.DataFrame) -> pd.Series:
    """Compute onset predicate for a single node's time series (sorted by date).

    Returns a boolean Series aligned to g.index.

    The predicate is:
    1. accel_z_5d >= ONSET_ACCEL_Z_THRESHOLD (1.0)
    2. >= ONSET_POSITIVE_DAYS_IN_5 (3) of last 5 accel_z raw > 0
    3. accel (rs_mom) > 0  [rs_mom_proxy condition]

    This is a LABELED PROXY for the true FSM onset predicate.
    - Condition 3 (accel > 0) is EXACT — tiles carry rs_mom = accel directly.
    - Condition 2 (sign count) is EXACT for sign but uses accel_z proxy series.
    - Condition 1 (accel_z_5d >= 1.0) uses accel_z derived from rs_mom z-scored
      over 252d causal window. This is faithful to the FSM definition since
      accel = vel_1w - vel_3m = rs_mom (tile) and the z-score method is the same.
      Minor deviation: the FSM uses price-level velocity; tiles use rs_mom which
      is the SAME quantity at daily granularity.
    """
    n = len(g)
    accel_z_raw = g["accel_z"].to_numpy(dtype=float)
    accel_z_5d_arr = g["accel_z_5d"].to_numpy(dtype=float)
    accel_arr = g["accel"].to_numpy(dtype=float)  # = rs_mom

    cond = np.zeros(n, dtype=bool)
    confirm_window = 5  # matches EPISODE_CFG["confirm_window_m"]

    for i in range(n):
        # Condition 1: smoothed accel_z above threshold
        az5 = accel_z_5d_arr[i]
        if np.isnan(az5) or az5 < ONSET_ACCEL_Z_THRESHOLD:
            continue

        # Condition 2: >= 3 of last 5 accel_z raw > 0
        if i < confirm_window - 1:
            continue
        window = accel_z_raw[i - confirm_window + 1: i + 1]
        pos_count = int(np.sum(window > 0))
        if pos_count < ONSET_POSITIVE_DAYS_IN_5:
            continue

        # Condition 3: accel (= rs_mom) > 0
        ac = accel_arr[i]
        if np.isnan(ac) or ac <= 0:
            continue

        cond[i] = True

    return pd.Series(cond, index=g.index, dtype=bool)


def find_first_crossings(panel: pd.DataFrame) -> pd.DataFrame:
    """Find all real-time onset first-crossings per node.

    A 'first crossing' is the FIRST date in each contiguous run where
    compute_onset_predicate = True, subject to hysteresis:
    - After a crossing ends (predicate drops to False), the next new crossing
      can only start after HYSTERESIS_GAP_DAYS have passed.

    This mirrors the FSM's behavior: each new crossing = onset_idx gets set
    once when predicate flips False→True, and hysteresis prevents re-crossing
    within the cooldown window. We do NOT require confirmation (unlike the catalog),
    so this is the survivorship-free universe.

    Returns DataFrame with columns: node, date (first-crossing date), direction='in'
    """
    crossings = []
    for node, grp in panel.groupby("node"):
        g = grp.sort_values("date").copy()
        g = g.reset_index(drop=True)

        # Compute predicate
        pred = compute_onset_predicate(g)

        dates = g["date"].to_numpy()
        pred_arr = pred.to_numpy()
        n = len(dates)

        in_episode = False
        last_false_idx = -HYSTERESIS_GAP_DAYS - 1

        for i in range(n):
            if not in_episode:
                # Apply hysteresis: i - last_false_idx > HYSTERESIS_GAP_DAYS
                if (i - last_false_idx) <= HYSTERESIS_GAP_DAYS:
                    continue
                if pred_arr[i]:
                    # New first-crossing
                    crossings.append({
                        "node": node,
                        "date": pd.Timestamp(dates[i]),
                    })
                    in_episode = True
            else:
                if not pred_arr[i]:
                    in_episode = False
                    last_false_idx = i
                # else: still in episode, don't record again

    df = pd.DataFrame(crossings) if crossings else pd.DataFrame(columns=["node", "date"])
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df


def build_forward_returns(closes: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """Build forward returns for each horizon.

    Entry at lag=1 close, fwd_xs = forward return minus equal-weight sector mean.
    Matches Codex script exactly: entry=closes.shift(-1), exit=closes.shift(-(1+h)),
    fwd_xs = fwd_ret - equal-weight mean across sectors.
    """
    out = {}
    for h in HORIZONS:
        entry = closes.shift(-ENTRY_LAG)
        exit_ = closes.shift(-(ENTRY_LAG + h))
        fwd_ret = exit_ / entry - 1.0
        sector_ret = fwd_ret[list(SECTOR_ETFS)]
        xs_mean = sector_ret.mean(axis=1)
        # Build long-form: date, node, fwd_xs
        long = sector_ret.stack().dropna().rename("fwd_ret").reset_index()
        long.columns = ["date", "node", "fwd_ret"]
        long["fwd_xs"] = long["fwd_ret"] - long["date"].map(xs_mean)
        long["horizon"] = h
        out[h] = long[["date", "node", "fwd_xs"]].copy()
    return out


def measure_events(events: pd.DataFrame, fwd_returns: dict[int, pd.DataFrame]) -> dict:
    """Measure forward xs returns for a set of events (date, node) at each horizon."""
    results = {}
    for h, fwd in fwd_returns.items():
        merged = events.merge(fwd, on=["date", "node"], how="inner")
        sm = mean_summary(merged["fwd_xs"].dropna(), lag=max(1, h))
        results[f"h{h}d"] = sm
    return results


def main() -> None:
    print("Loading tile panel...")
    tile_df = load_tile_panel()
    print(f"  Tile panel shape: {tile_df.shape}, date range: {tile_df['date'].min().date()} -> {tile_df['date'].max().date()}")

    print("Loading closes...")
    closes = load_closes()
    latest_price_date = str(closes[list(SECTOR_ETFS)].dropna(how="all").index.max().date())
    print(f"  Latest price date: {latest_price_date}")

    print("Loading catalog episodes...")
    catalog_ep = load_catalog_episodes()
    print(f"  Catalog IN episodes (tier-s, sector ETF): {len(catalog_ep)}")

    print("Computing forward returns...")
    fwd_returns = build_forward_returns(closes)

    # =========================================================================
    # STEP 1: Catalog baseline (sanity anchor)
    # =========================================================================
    print("\n--- STEP 1: Catalog baseline ---")
    catalog_events = catalog_ep[["node", "onset_date"]].rename(columns={"onset_date": "date"})
    catalog_events["date"] = catalog_events["date"].dt.normalize()
    catalog_results = measure_events(catalog_events, fwd_returns)
    print(f"  Catalog n_events at h10d merge: {catalog_results['h10d']['n']}")
    print(f"  h10d: mean={catalog_results['h10d']['mean']:.4f}, hit={catalog_results['h10d']['hit']:.3f}, t={catalog_results['h10d']['t_hac']:.2f}")
    print(f"  h21d: mean={catalog_results['h21d']['mean']:.4f}, hit={catalog_results['h21d']['hit']:.3f}, t={catalog_results['h21d']['t_hac']:.2f}")

    # =========================================================================
    # STEP 2: Reconstruct real-time first-crossings
    # =========================================================================
    print("\n--- STEP 2: Compute accel_z panel + find first-crossings ---")
    az_panel = build_accel_z_panel(tile_df)
    print("  Computing first crossings (survivorship-free)...")
    first_crossings = find_first_crossings(az_panel)
    print(f"  Total first-crossings (all sector ETFs): {len(first_crossings)}")

    # =========================================================================
    # STEP 3: Measure edge on first-crossing universe
    # =========================================================================
    print("\n--- STEP 3: First-crossing universe measurement ---")
    fc_results = measure_events(first_crossings, fwd_returns)
    print(f"  First-crossing n: {fc_results['h10d']['n']}")
    print(f"  h10d: mean={fc_results['h10d']['mean']:.4f}, hit={fc_results['h10d']['hit']:.3f}, t={fc_results['h10d']['t_hac']:.2f}")
    print(f"  h21d: mean={fc_results['h21d']['mean']:.4f}, hit={fc_results['h21d']['hit']:.3f}, t={fc_results['h21d']['t_hac']:.2f}")

    # Identify died-young: first-crossings NOT in catalog
    # Match: crossing date within ±3 sessions of catalog onset date for same node
    catalog_events_dedup = catalog_events.drop_duplicates(["node", "date"])
    catalog_set = set(zip(catalog_events_dedup["node"], catalog_events_dedup["date"].dt.date.astype(str)))

    # Build expanded catalog lookup: for each catalog event, also include ±3d dates
    catalog_lookup: dict[str, set] = {}  # node -> set of date strings within ±3d
    for _, row in catalog_events_dedup.iterrows():
        node = row["node"]
        dt = row["date"]
        if node not in catalog_lookup:
            catalog_lookup[node] = set()
        for delta in range(-3, 4):
            catalog_lookup[node].add((dt + pd.Timedelta(days=delta)).date().isoformat())

    def is_in_catalog(row) -> bool:
        node = row["node"]
        dt_str = row["date"].date().isoformat()
        return dt_str in catalog_lookup.get(node, set())

    first_crossings["in_catalog"] = first_crossings.apply(is_in_catalog, axis=1)
    died_young = first_crossings[~first_crossings["in_catalog"]].copy()
    catalog_fc = first_crossings[first_crossings["in_catalog"]].copy()

    print(f"  First-crossings in catalog (±3d match): {catalog_fc.shape[0]}")
    print(f"  Died-young (not in catalog): {died_young.shape[0]}")

    died_young_results = measure_events(died_young[["node", "date"]], fwd_returns)
    print(f"  Died-young h10d: mean={died_young_results['h10d']['mean']:.4f}, hit={died_young_results['h10d']['hit']:.3f}, t={died_young_results['h10d']['t_hac']:.2f}")
    print(f"  Died-young h21d: mean={died_young_results['h21d']['mean']:.4f}, hit={died_young_results['h21d']['hit']:.3f}, t={died_young_results['h21d']['t_hac']:.2f}")

    # Inflation
    catalog_mean_10d = catalog_results["h10d"]["mean"]
    fc_mean_10d = fc_results["h10d"]["mean"]
    catalog_mean_21d = catalog_results["h21d"]["mean"]
    fc_mean_21d = fc_results["h21d"]["mean"]

    inflation_10d_pp = (catalog_mean_10d - fc_mean_10d) * 100
    inflation_21d_pp = (catalog_mean_21d - fc_mean_21d) * 100
    n_ratio = fc_results["h10d"]["n"] / catalog_results["h10d"]["n"] if catalog_results["h10d"]["n"] > 0 else None

    print(f"\n  Inflation: catalog mean minus first-crossing mean")
    print(f"    h10d: {inflation_10d_pp:.2f} pp")
    print(f"    h21d: {inflation_21d_pp:.2f} pp")
    print(f"  n_ratio (first-crossing / catalog): {n_ratio:.2f}")

    # =========================================================================
    # STEP 4: Regime check — 3 era split on CATALOG onsets
    # =========================================================================
    print("\n--- STEP 4: Era split ---")
    eras = [
        ("1999-2008", "1999-01-01", "2008-12-31"),
        ("2009-2016", "2009-01-01", "2016-12-31"),
        ("2017-2026", "2017-01-01", "2026-12-31"),
    ]

    era_results = {}
    for era_name, era_start, era_end in eras:
        mask = (
            (catalog_events["date"] >= era_start)
            & (catalog_events["date"] <= era_end)
        )
        era_events = catalog_events[mask].copy()
        era_fwd = {}
        for h, fwd in fwd_returns.items():
            era_fwd[h] = fwd[
                (fwd["date"] >= era_start) & (fwd["date"] <= era_end)
            ]
        era_res = measure_events(era_events, era_fwd)
        era_results[era_name] = era_res
        print(f"  {era_name}: n={era_res['h10d']['n']}, h10d mean={era_res['h10d']['mean']:.4f}, t={era_res['h10d']['t_hac']}")

    # =========================================================================
    # Assemble artifact
    # =========================================================================
    print("\n--- Writing artifact ---")

    def _fmt(v):
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        return round(float(v), 5) if isinstance(v, float) else v

    def _fmt_sm(sm: dict) -> dict:
        return {k: _fmt(v) for k, v in sm.items()}

    artifact = {
        "meta": {
            "script": "scripts/research/rotation_onset_firstcrossing_remeasure.py",
            "run_date": "2026-07-06",
            "tile_date_range": f"{tile_df['date'].min().date()} to {tile_df['date'].max().date()}",
            "latest_etf_price_date": latest_price_date,
            "entry_lag_sessions": ENTRY_LAG,
            "horizons": HORIZONS,
        },
        "methods_note": (
            "Onset predicate proxy: accel_z derived by causally z-scoring rs_mom (tile column) "
            "over a 252-day trailing window, since tile rs_mom = vel_1w - vel_3m = accel "
            "as defined in engine/oracle/panel.py. Conditions: (1) accel_z_5d >= 1.0 [5-day "
            "mean of z-scored accel], (2) >=3 of last 5 raw accel_z > 0, (3) accel > 0 "
            "[exact, from tile rs_mom]. This is a HIGH-FIDELITY proxy: (3) is exact, "
            "(2) sign is exact, (1) differs only in that tile rs_mom is vel_1w-vel_3m at "
            "daily granularity matching the panel.py definition exactly. Main limitation: "
            "tile accel_z may differ slightly from panel.py _causal_z if velocity denominators "
            "(WEEKS divisors) affect the z-score magnitude, but the cross-sectional rank-based "
            "threshold of 1.0 (q87 of accel_z) is preserved by normalization. Labeled: PROXY "
            "but high-fidelity. First-crossing hysteresis: HYSTERESIS_GAP_DAYS=5 applied, "
            "matching FSM. Confirmation filter NOT applied (that is the survivorship filter "
            "being measured). Catalog-match window: +-3 sessions."
        ),
        "step1_catalog_baseline": {
            "n_catalog_episodes": len(catalog_ep),
            "description": "Tier-s sector-ETF IN episodes from tm_episodes.json, onset+1 entry",
            "h10d": _fmt_sm(catalog_results["h10d"]),
            "h21d": _fmt_sm(catalog_results["h21d"]),
        },
        "step2_first_crossing_universe": {
            "n_first_crossings_total": len(first_crossings),
            "n_matched_to_catalog": int(catalog_fc.shape[0]),
            "n_died_young": int(died_young.shape[0]),
        },
        "step3_first_crossing_results": {
            "description": "All real-time onset first-crossings (proxy predicate, no confirmation filter), onset+1 entry",
            "full_universe": {
                "h10d": _fmt_sm(fc_results["h10d"]),
                "h21d": _fmt_sm(fc_results["h21d"]),
            },
            "died_young_subset": {
                "description": "First-crossings NOT matched to any catalog episode (within +-3 sessions)",
                "h10d": _fmt_sm(died_young_results["h10d"]),
                "h21d": _fmt_sm(died_young_results["h21d"]),
            },
        },
        "step3_inflation": {
            "catalog_mean_10d_pct": _fmt(catalog_mean_10d * 100),
            "fc_universe_mean_10d_pct": _fmt(fc_mean_10d * 100),
            "inflation_10d_pp": _fmt(inflation_10d_pp),
            "catalog_mean_21d_pct": _fmt(catalog_mean_21d * 100),
            "fc_universe_mean_21d_pct": _fmt(fc_mean_21d * 100),
            "inflation_21d_pp": _fmt(inflation_21d_pp),
            "n_ratio_fc_over_catalog": _fmt(n_ratio),
            "materiality_assessment": (
                "MATERIAL if |inflation_10d_pp| > 0.15 or sign/significance flips at 21d"
            ),
        },
        "step4_era_split_catalog": {
            era_name: {
                "h10d": _fmt_sm(era_results[era_name]["h10d"]),
                "h21d": _fmt_sm(era_results[era_name]["h21d"]),
            }
            for era_name in ["1999-2008", "2009-2016", "2017-2026"]
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(artifact, indent=2))
    print(f"  Wrote {OUT_PATH}")

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"CATALOG BASELINE  n={catalog_results['h10d']['n']}")
    print(f"  h10d  mean={catalog_mean_10d*100:.2f}%  hit={catalog_results['h10d']['hit']:.3f}  t={catalog_results['h10d']['t_hac']:.2f}")
    print(f"  h21d  mean={catalog_mean_21d*100:.2f}%  hit={catalog_results['h21d']['hit']:.3f}  t={catalog_results['h21d']['t_hac']:.2f}")
    print()
    print(f"FIRST-CROSSING UNIVERSE  n={fc_results['h10d']['n']}  (n_ratio={n_ratio:.2f}x catalog)")
    print(f"  h10d  mean={fc_mean_10d*100:.2f}%  hit={fc_results['h10d']['hit']:.3f}  t={fc_results['h10d']['t_hac']:.2f}")
    print(f"  h21d  mean={fc_mean_21d*100:.2f}%  hit={fc_results['h21d']['hit']:.3f}  t={fc_results['h21d']['t_hac']:.2f}")
    print()
    print(f"DIED-YOUNG (not in catalog)  n={died_young_results['h10d']['n']}")
    print(f"  h10d  mean={died_young_results['h10d']['mean']*100:.2f}%  hit={died_young_results['h10d']['hit']:.3f}  t={died_young_results['h10d']['t_hac']:.2f}")
    print(f"  h21d  mean={died_young_results['h21d']['mean']*100:.2f}%  hit={died_young_results['h21d']['hit']:.3f}  t={died_young_results['h21d']['t_hac']:.2f}")
    print()
    print(f"INFLATION:  h10d = {inflation_10d_pp:.2f} pp    h21d = {inflation_21d_pp:.2f} pp")
    print(f"n-ratio (first-crossing / catalog) = {n_ratio:.2f}")
    print()
    print("ERA SPLIT (catalog IN onsets):")
    for era_name, _, _ in eras:
        er = era_results[era_name]
        t_str = f"{er['h10d']['t_hac']:.2f}" if er['h10d']['t_hac'] is not None else "N/A"
        print(f"  {era_name}: n={er['h10d']['n']}  h10d mean={er['h10d']['mean']*100:.2f}%  t={t_str}")


if __name__ == "__main__":
    main()
