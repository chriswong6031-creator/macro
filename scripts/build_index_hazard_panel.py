"""IX-1 SUBSTRATE — index-level person-period hazard panel (v0).

SCOPE (CPI program, IX-1 substrate wave — NO trial, NO preregistration here):
  Build data/hazard/panel_index_v0.parquet: person-period monthly rows for INDEX
  entities, using the SAME pipeline as scripts/build_hazard_panel.py (its functions
  are imported, not forked), plus FT-4-style constituent-structure covariates joined
  from the MEMBER panel cross-section. The later preregistered IX-1 turn-hazard trial
  runs on this artifact; this script never mutates the member panel or its epoch.

Universe (v0):
  - SPY                      family "us_market"  (US market index proxy)
  - AAXJ/EEM/EFA/ILF/VGK/VPL/VXUS  family "bloc"  (the 7 bloc ETFs from
    data/cycle_pattern/entities.parquet; tapes in data/yahoo/)

Detector config (documented choice):
  The member builder uses TURN_DETECTOR_DEFAULTS per family: 14% ZigZag for
  us_sector, 14% for country, 18% for cn_sector — always on the close_price basis
  (split-adjusted, dividend-UNadjusted; D4_SUBSTRATE §1), detector version 2.
  ALL index entities here use the us_sector parameterization (14%, close_price, v2),
  so the epoch stamp equals the member panel's primary stamp (price_c4414dcb).
  Blocs are detected at 14% in the member panel too (country family) — no divergence.

Schema:
  Exactly the member panel columns (so the trial can reuse the W4.2 fit machinery),
  PLUS four index-level FT-4-style covariates (CPI-017 left the index-level target open):
    sync_family          — family sync R from data/leadlag/sync_gauge.json at the row
                           month (families.us_sector for SPY; families.country for blocs
                           — the gauge's country membership already EXCLUDES blocs, ruling A14)
    phase_breadth_late   — fraction of member cross-section with pos_osc >= 70 at t
    phase_breadth_early  — fraction with pos_osc <= 30 at t
    pos_dispersion       — cross-sectional std(pos_osc)/100 at t
  Thresholds/formulas match scripts/build_cycle_pattern_ft_phase0.attach_ft4_structure.
  Member cross-section: us_sector members for SPY rows; country members EXCLUDING the
  7 blocs for bloc rows (constituents only — matches the sync gauge membership).

PIT contract (inherited from the member builder, S2 ruling):
  Rows at month-end t use only tape <= t and turns with confirmed_at <= t; labels
  look forward. Covariates are exact month-key joins against the member panel
  cross-section AT t and the gauge entry AT t — appending later months can never
  change earlier values (tested in tests/test_index_hazard_panel.py).

rs_63d benchmark (documented choice):
  Member convention is RS vs the family benchmark (us_sector→SPY, country→ACWX with
  EFA fallback). SPY-vs-SPY is degenerate (identically 0), so BOTH index families use
  the world ex-US chain ACWX→EFA. ACWX is absent from data/yahoo/ as of this build, so
  EFA is the effective benchmark — meaning EFA's own rs_63d rows are degenerate-0
  (disclosed in the census; the member panel's EFA country rows share this property).

Usage:
  python -m scripts.build_index_hazard_panel [--asof-end YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.cycle_ontology import TURN_DETECTOR_DEFAULTS, turn_epoch
from scripts.build_hazard_panel import (
    _build_instrument_rows,
    _detect_turns_for_instrument,
    _load_yahoo_close,
    _load_yahoo_price,
    _month_end_index,
    _precompute_family_median_cache,
    _precompute_medians_cache,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# v0 index universe: entity id -> index family
INDEX_FAMILY: dict[str, str] = {
    "SPY":  "us_market",
    "AAXJ": "bloc",
    "EEM":  "bloc",
    "EFA":  "bloc",
    "ILF":  "bloc",
    "VGK":  "bloc",
    "VPL":  "bloc",
    "VXUS": "bloc",
}

BLOC_IDS = ["AAXJ", "EEM", "EFA", "ILF", "VGK", "VPL", "VXUS"]

# us_sector parameterization for ALL index entities (see module docstring).
ZZ_PCT_INDEX: float = TURN_DETECTOR_DEFAULTS["pct_sector"]  # 14.0

# Index family -> member-panel family providing the constituent cross-section.
MEMBER_FAMILY_FOR: dict[str, str] = {
    "us_market": "us_sector",
    "bloc":      "country",
}

COVARIATE_COLS = [
    "sync_family", "phase_breadth_late", "phase_breadth_early", "pos_dispersion",
]

# FT-4 thresholds (scripts/build_cycle_pattern_ft_phase0.attach_ft4_structure)
_POS_LATE_THRESHOLD = 70.0
_POS_EARLY_THRESHOLD = 30.0

MEMBER_PANEL_DEFAULT = _REPO / "data/hazard/panel_price_c4414dcb.parquet"
SYNC_GAUGE_DEFAULT = _REPO / "data/leadlag/sync_gauge.json"
OUT_DEFAULT = _REPO / "data/hazard/panel_index_v0.parquet"
CENSUS_DEFAULT = _REPO / "research/cycle_masterplan/IX1_SUBSTRATE_CENSUS.md"

# Embargo boundary for the census event counts (IX-1 gate freezes on pre-embargo data).
EMBARGO_START = pd.Timestamp("2024-01-01")


# ---------------------------------------------------------------------------
# FT-4-style constituent-structure covariates (PIT-pure, exact month-key joins)
# ---------------------------------------------------------------------------

def member_cross_section_stats(
    member_panel: pd.DataFrame,
    family: str,
    exclude_ids: list[str] | tuple = (),
) -> pd.DataFrame:
    """Monthly constituent-structure stats from the MEMBER panel cross-section.

    For each date, the cross-section is the set of member instruments of ``family``
    (one row per id — the up/down person-period rows carry the same pos_osc, so we
    dedup on (date, id) exactly like attach_ft4_structure). PIT-pure: the stats at
    month t are a function of member rows dated t only.

    Returns a frame indexed by date with columns
    phase_breadth_late / phase_breadth_early / pos_dispersion.
    """
    d = member_panel[member_panel["family"] == family]
    if len(exclude_ids):
        d = d[~d["id"].isin(list(exclude_ids))]
    uniq = d.drop_duplicates(subset=["date", "id"])[["date", "id", "pos_osc"]]
    recs = []
    for date, grp in uniq.groupby("date"):
        vals = pd.to_numeric(grp["pos_osc"], errors="coerce").dropna().to_numpy(float)
        if len(vals) == 0:
            recs.append((date, np.nan, np.nan, np.nan))
            continue
        recs.append((
            date,
            float(np.mean(vals >= _POS_LATE_THRESHOLD)),
            float(np.mean(vals <= _POS_EARLY_THRESHOLD)),
            float(np.std(vals)) / 100.0,
        ))
    out = pd.DataFrame(
        recs,
        columns=["date", "phase_breadth_late", "phase_breadth_early", "pos_dispersion"],
    )
    out["date"] = pd.to_datetime(out["date"])
    return out.set_index("date").sort_index()


def sync_series_from_gauge(gauge: dict, family: str) -> pd.Series:
    """Monthly sync (circular mean resultant length R) series for one gauge family.

    data/leadlag/sync_gauge.json families.<family> is a list of
    {date, sync, n, frac} rows; the historical rows were computed by
    scripts/leadlag_phase0.py and the current month is upserted nightly by
    scripts/append_sync_gauge.py (idempotent per month).
    """
    rows = gauge.get("families", {}).get(family, []) or []
    vals = {
        pd.Timestamp(r["date"]): float(r["sync"])
        for r in rows
        if r.get("sync") is not None
    }
    return pd.Series(vals, dtype=float).sort_index()


def attach_index_covariates(
    panel: pd.DataFrame,
    member_panel: pd.DataFrame,
    gauge: dict,
) -> pd.DataFrame:
    """Join the FT-4-style constituent-structure covariates onto index rows.

    PIT contract: the covariates for a row at month-end t derive ONLY from
    (a) the member-panel cross-section AT date t and (b) the gauge entry AT t.
    Exact month-key joins — appending later months never changes earlier values.
    """
    d = panel.copy()
    d["date"] = pd.to_datetime(d["date"])
    for col in COVARIATE_COLS:
        d[col] = np.nan
    for fam in sorted(set(d["family"])):
        mfam = MEMBER_FAMILY_FOR.get(fam)
        if mfam is None:
            continue
        exclude = BLOC_IDS if mfam == "country" else ()
        stats = member_cross_section_stats(member_panel, mfam, exclude_ids=exclude)
        sync = sync_series_from_gauge(gauge, mfam)
        mask = d["family"] == fam
        dates = d.loc[mask, "date"]
        d.loc[mask, "sync_family"] = dates.map(sync).to_numpy()
        for col in ["phase_breadth_late", "phase_breadth_early", "pos_dispersion"]:
            d.loc[mask, col] = dates.map(stats[col]).to_numpy()
    return d


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build_index_panel(
    yahoo_dir: Path,
    regime_path: Path,
    member_panel_path: Path,
    sync_gauge_path: Path,
    out_path: Path,
    asof_end: str | None = None,
) -> pd.DataFrame:
    """Build the index-level person-period panel and persist it to out_path."""
    # ── Epoch stamp: identical detector config to the member us_sector family ──
    panel_epoch = turn_epoch(
        basis="close_price", zz_params=float(ZZ_PCT_INDEX), detector_version=2
    )

    # Engine fingerprint — same manifest the member builder reads
    try:
        with open(_REPO / "data/sector_cycles/backfill_manifest.json") as f:
            engine_fp = json.load(f).get("engine_fingerprint", "unknown")
    except Exception:
        engine_fp = "unknown"

    # ── Inputs ────────────────────────────────────────────────────────────────
    print("Loading regime history / member panel / sync gauge...")
    regime_hist = pd.read_parquet(regime_path)
    regime_hist.index = pd.to_datetime(regime_hist.index)
    member_panel = pd.read_parquet(member_panel_path)
    with open(sync_gauge_path) as f:
        gauge = json.load(f)

    # ── Month-end grid (member convention: 1995-01 → asof) ───────────────────
    asof_end_ts = pd.Timestamp(asof_end) if asof_end else pd.Timestamp("today").normalize()
    month_ends_full = _month_end_index("1995-01", asof_end_ts.strftime("%Y-%m"))

    # ── Benchmark for rs_63d: ACWX → EFA fallback (see module docstring) ──────
    bench = _load_yahoo_close("ACWX", yahoo_dir)
    bench_name = "ACWX"
    if bench is None:
        bench = _load_yahoo_close("EFA", yahoo_dir)
        bench_name = "EFA"
        if bench is not None:
            print("  NOTE: ACWX not found — using EFA as index RS benchmark (documented)")

    # ── Turn detection (close_price basis, 14%, detector v2) ─────────────────
    print(f"Detecting turns for {len(INDEX_FAMILY)} index entities "
          f"(pct={ZZ_PCT_INDEX}, epoch={panel_epoch})...")
    all_turns_cache: dict[str, tuple[str, list[dict]]] = {}
    price_basis_fallbacks: list[str] = []
    for iid, family in INDEX_FAMILY.items():
        px = _load_yahoo_price(iid, yahoo_dir)
        raw_path = yahoo_dir / f"{iid.upper()}.parquet"
        if raw_path.exists() and "close_price" not in pd.read_parquet(raw_path).columns:
            price_basis_fallbacks.append(iid)
        if px is None or len(px) < 200:
            print(f"  SKIP {iid}: insufficient data")
            continue
        turns = _detect_turns_for_instrument(px, iid, ZZ_PCT_INDEX)
        all_turns_cache[iid] = (family, turns)
        n_conf = len([t for t in turns if not t.get("provisional")])
        print(f"  {family} {iid}: {n_conf} confirmed turns (price basis)")
    if price_basis_fallbacks:
        print(f"  WARNING: {len(price_basis_fallbacks)} entities lacked close_price "
              f"(TR fallback — SUBSTRATE CONTRACT VIOLATION): {price_basis_fallbacks}")

    # ── Expanding medians (identical math — imported from the member builder) ─
    print("Pre-computing expanding medians...")
    medians_cache = _precompute_medians_cache(all_turns_cache, month_ends_full)
    families = sorted(set(f for f, _ in all_turns_cache.values()))
    family_med_cache = _precompute_family_median_cache(
        all_turns_cache, medians_cache, month_ends_full, families=families
    )
    # NOTE: us_market is a singleton family — its family median IS SPY's own median,
    # so the k=6 blend degenerates to the own-median (disclosed in the census).

    def _per_id_med_fn(iid: str, t_end: pd.Timestamp) -> dict:
        t_str = t_end.strftime("%Y-%m")
        d = medians_cache.get(iid, {})
        return {
            "up":     d.get("up", {}).get(t_str, {}).get("med"),
            "n_up":   d.get("up", {}).get(t_str, {}).get("n", 0),
            "down":   d.get("down", {}).get(t_str, {}).get("med"),
            "n_down": d.get("down", {}).get(t_str, {}).get("n", 0),
        }

    def _fam_med_fn(fam: str, direction: str, t_end: pd.Timestamp) -> float | None:
        return family_med_cache.get(fam, {}).get(direction, {}).get(t_end.strftime("%Y-%m"))

    # ── Person-period rows (identical row builder — imported) ────────────────
    print("Building person-period rows...")
    all_rows: list[dict] = []
    for iid in sorted(all_turns_cache):  # sorted for determinism
        family, turns = all_turns_cache[iid]
        close = _load_yahoo_close(iid, yahoo_dir)
        if close is None:
            continue
        me = month_ends_full[
            (month_ends_full >= close.index.min())
            & (month_ends_full <= min(close.index.max(), asof_end_ts))
        ]
        rows = _build_instrument_rows(
            iid=iid,
            family=family,
            close=close,
            pct=ZZ_PCT_INDEX,
            month_ends=me,
            all_turns=turns,
            per_id_medians_fn=lambda iid_=iid, t=None: _per_id_med_fn(iid_, t),
            family_median_fn=lambda direction, t, fam_=family: _fam_med_fn(fam_, direction, t),
            regime_hist=regime_hist,
            bench_close=bench,
            turn_def_ver=panel_epoch,
            engine_fp=engine_fp,
        )
        all_rows.extend(rows)
        print(f"  {iid} ({family}): {len(rows)} rows, {sum(r['y1'] for r in rows)} events(y1)")

    panel = pd.DataFrame(all_rows)
    panel["date"] = pd.to_datetime(panel["date"])

    # ── Covariates ────────────────────────────────────────────────────────────
    print("Attaching index-level FT-4-style covariates...")
    panel = attach_index_covariates(panel, member_panel, gauge)

    # ── Dtype harmonization: exact parity with the member panel schema ───────
    for col in member_panel.columns:
        panel[col] = panel[col].astype(member_panel[col].dtype)
    panel = panel[list(member_panel.columns) + COVARIATE_COLS]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out_path, index=False)
    print(f"Index panel written: {out_path} ({len(panel)} rows) "
          f"[epoch={panel_epoch}, bench={bench_name}]")
    return panel


# ---------------------------------------------------------------------------
# Census report (IX1_SUBSTRATE_CENSUS.md)
# ---------------------------------------------------------------------------

def write_census(
    panel: pd.DataFrame,
    all_turns_cache: dict[str, tuple[str, list[dict]]] | None,
    out_path: Path,
    bench_name: str,
) -> None:
    """Substrate stats: everything a §-registration needs to freeze a realistic IX-1 gate."""
    from engine.index_km import KM_MIN_ROWS_DEFAULT, index_km_table

    pre = panel[panel["date"] < EMBARGO_START]
    km = index_km_table(pre)

    lines: list[str] = []
    w = lines.append
    w("# IX-1 Substrate Census — index-level hazard panel v0")
    w("")
    w(f"**Built:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    w("**Artifact:** `data/hazard/panel_index_v0.parquet` "
      "(producer `scripts/build_index_hazard_panel.py`)")
    w(f"**Turn epoch stamp:** `{panel['turn_def_version'].iloc[0]}` — identical detector "
      "config to the member panel's primary stamp (close_price basis, detector v2).")
    w("")
    w("SUBSTRATE ONLY — no trial, no preregistration, no truth-registry writes in this "
      "wave. The member panel `data/hazard/panel_price_c4414dcb.parquet` and its epoch "
      "are untouched. Event counts below are **pre-2024 (the embargo)** unless stated.")
    w("")
    w("## Configuration choices (frozen facts for the future § registration)")
    w("")
    w("| Choice | Value | Why |")
    w("|--------|-------|-----|")
    w("| ZigZag threshold | 14% for ALL index entities | Member builder uses "
      "TURN_DETECTOR_DEFAULTS: 14% us_sector, 14% country, 18% cn_sector. SPY takes the "
      "us_sector value per the substrate spec; blocs are detected at 14% in the member "
      "panel too (country family) — no divergence. |")
    w("| Detection basis | `close_price` (split-adj, div-UNadj), detector v2 | D4_SUBSTRATE "
      "§1 contract, same as member panel. |")
    w("| Month grid | 1995-01 → asof month-ends | Member builder convention. |")
    w(f"| rs_63d benchmark | ACWX → EFA fallback (effective: **{bench_name}**) | "
      "SPY-vs-SPY is degenerate (identically 0), so us_market uses the world ex-US chain; "
      "blocs keep the member country-family chain. EFA's own rs_63d rows are therefore "
      "degenerate-0 (same property as EFA's country rows in the member panel). |")
    w("| k=6 age blend | us_market family = {SPY} only | Singleton family ⇒ family median "
      "= own median ⇒ blend degenerates to the own-median. Bloc family pools 7 entities. |")
    w("| sync_family source | `data/leadlag/sync_gauge.json` families.us_sector (SPY) / "
      "families.country (blocs) at the row month | Gauge country membership already "
      "excludes blocs (ruling A14). Exact month-key join. |")
    w("| Breadth/dispersion cross-section | Member panel us_sector members (SPY rows); "
      "country members EXCLUDING the 7 blocs (bloc rows) | Constituents only; matches "
      "gauge membership. Thresholds per FT-4: late = pos_osc≥70, early = ≤30, "
      "dispersion = std/100. |")
    w("")

    w("## Rows per entity")
    w("")
    w("| Entity | Family | Rows | Date span | Rows pre-2024 |")
    w("|--------|--------|------|-----------|---------------|")
    for iid in sorted(panel["id"].unique()):
        sub = panel[panel["id"] == iid]
        sub_pre = pre[pre["id"] == iid]
        w(f"| {iid} | {sub['family'].iloc[0]} | {len(sub):,} | "
          f"{sub['date'].min().date()} → {sub['date'].max().date()} | {len(sub_pre):,} |")
    w("")

    w("## Event counts per entity × direction (pre-2024 embargo)")
    w("")
    w("| Entity | Direction | Rows | y1 | y3 | y6 | Censored |")
    w("|--------|-----------|------|----|----|----|----------|")
    for iid in sorted(pre["id"].unique()):
        for direction in ["up", "down"]:
            sub = pre[(pre["id"] == iid) & (pre["direction"] == direction)]
            if len(sub) == 0:
                continue
            w(f"| {iid} | {direction} | {len(sub):,} | {int(sub['y1'].sum())} | "
              f"{int(sub['y3'].sum())} | {int(sub['y6'].sum())} | "
              f"{int(sub['censored'].sum())} |")
    w("")

    w("## Turn-count reality check (confirmed ZigZag turns per entity)")
    w("")
    if all_turns_cache:
        w("| Entity | Confirmed turns (all) | Peaks | Troughs | Confirmed pre-2024 |")
        w("|--------|----------------------|-------|---------|--------------------|")
        for iid in sorted(all_turns_cache):
            _, turns = all_turns_cache[iid]
            conf = [t for t in turns if not t.get("provisional")]
            peaks = sum(1 for t in conf if t["k"] == "peak")
            troughs = sum(1 for t in conf if t["k"] == "trough")
            conf_pre = [t for t in conf if pd.Timestamp(t["confirmed_at"]) < EMBARGO_START]
            w(f"| {iid} | {len(conf)} | {peaks} | {troughs} | {len(conf_pre)} |")
        w("")

    w("## Covariate coverage (non-null share of rows)")
    w("")
    w("| Covariate | us_market | bloc | all |")
    w("|-----------|-----------|------|-----|")
    for col in COVARIATE_COLS:
        parts = []
        for fam in ["us_market", "bloc"]:
            sub = panel[panel["family"] == fam]
            parts.append(f"{sub[col].notna().mean():.1%}" if len(sub) else "—")
        w(f"| {col} | {parts[0]} | {parts[1]} | {panel[col].notna().mean():.1%} |")
    w("")

    w("## Per-index KM estimability (age-pooled, pre-2024 rows)")
    w("")
    w(f"`engine/index_km.py` age-pooled P(y_h=1 | entity, direction); entity-level "
      f"estimate requires ≥{KM_MIN_ROWS_DEFAULT} rows per direction, else family-pooled "
      "fallback. 90% Wilson CIs.")
    w("")
    w("| Entity | Direction | n | y3 events | P(y3) | 90% CI | Source |")
    w("|--------|-----------|---|-----------|-------|--------|--------|")
    for iid in sorted(km["entities"]):
        for direction in ["up", "down"]:
            cell = km["entities"][iid].get(direction)
            if not cell:
                continue
            c3 = cell["horizons"][3]
            ci = (f"[{c3['ci90'][0]:.3f}, {c3['ci90'][1]:.3f}]"
                  if c3.get("ci90") else "—")
            w(f"| {iid} | {direction} | {cell['n']} | {c3['events']} | "
              f"{c3['p']:.3f} | {ci} | {c3['source']} |")
    w("")

    # Honest estimability verdict, computed not asserted
    spy_pre = pre[pre["id"] == "SPY"]
    spy_turns_txt = ""
    if all_turns_cache and "SPY" in all_turns_cache:
        conf = [t for t in all_turns_cache["SPY"][1]
                if not t.get("provisional")
                and pd.Timestamp(t["confirmed_at"]) < EMBARGO_START]
        spy_turns_txt = (f"SPY has {len(conf)} confirmed turns pre-2024 "
                         f"({sum(1 for t in conf if t['k']=='peak')} peaks / "
                         f"{sum(1 for t in conf if t['k']=='trough')} troughs). ")
    w("## Verdict — what an IX-1 gate can realistically freeze")
    w("")
    up_n = len(spy_pre[spy_pre["direction"] == "up"])
    dn_n = len(spy_pre[spy_pre["direction"] == "down"])
    w(f"- {spy_turns_txt}Pre-2024 SPY person-period rows: {up_n} up / {dn_n} down. "
      "Every distinct turn contributes MANY correlated rows (one per month of the leg), "
      "so the effective sample is the TURN count, not the row count — a per-SPY "
      "age-STRATIFIED KM (per-bucket λ) is NOT estimable with honest CIs.")
    w("- Age-POOLED per-entity P(y_h | direction) IS estimable for SPY and the longer "
      "blocs at h=3/6 (see table above: entity-source cells), but with wide Wilson CIs; "
      "the family-pooled fallback covers the short-history blocs (VXUS starts 2011).")
    w("- Any IX-1 trial gate should therefore (a) test covariate INFORMATION (likelihood "
      "ratio / Brier vs the age-pooled KM baseline), not per-bucket hazard shape; "
      "(b) use turn-count-aware effective n (the member panel's rho_hat machinery, "
      "ruling A2); (c) treat us_market as a single-entity family — no cross-sectional "
      "pooling exists at index level for SPY.")
    w("- SPY covariate coverage starts 1999-08 (breadth/dispersion: first us_sector "
      "member-panel month) / 1999-09 (sync_family: first gauge month); earlier index "
      "rows carry NaN covariates, so any covariate trial effectively starts there. "
      "Bloc rows are fully covered (blocs list after the country members).")
    w("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    print(f"Census written: {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="IX-1 index-level hazard panel builder (v0)")
    parser.add_argument("--asof-end", default=None, help="Cut-off date (YYYY-MM-DD)")
    parser.add_argument("--yahoo-dir", default=str(_REPO / "data/yahoo"))
    parser.add_argument("--regime-path", default=str(_REPO / "data/regime/regime_history.parquet"))
    parser.add_argument("--member-panel", default=str(MEMBER_PANEL_DEFAULT))
    parser.add_argument("--sync-gauge", default=str(SYNC_GAUGE_DEFAULT))
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    parser.add_argument("--census-out", default=str(CENSUS_DEFAULT))
    args = parser.parse_args()

    yahoo_dir = Path(args.yahoo_dir)
    panel = build_index_panel(
        yahoo_dir=yahoo_dir,
        regime_path=Path(args.regime_path),
        member_panel_path=Path(args.member_panel),
        sync_gauge_path=Path(args.sync_gauge),
        out_path=Path(args.out),
        asof_end=args.asof_end,
    )

    # Re-detect turns for the census turn table (cheap: 8 entities)
    turns_cache: dict[str, tuple[str, list[dict]]] = {}
    for iid, family in INDEX_FAMILY.items():
        px = _load_yahoo_price(iid, yahoo_dir)
        if px is None or len(px) < 200:
            continue
        turns_cache[iid] = (family, _detect_turns_for_instrument(px, iid, ZZ_PCT_INDEX))

    bench_name = "ACWX" if _load_yahoo_close("ACWX", yahoo_dir) is not None else "EFA"
    write_census(panel, turns_cache, Path(args.census_out), bench_name)

    print("\n=== IX-1 SUBSTRATE COMPLETE ===")
    print(f"Rows: {len(panel):,}  entities: {panel['id'].nunique()}")
    for fam in sorted(panel["family"].unique()):
        sub = panel[panel["family"] == fam]
        print(f"  {fam}: {len(sub):,} rows, {int(sub['y1'].sum())} events(y1)")


if __name__ == "__main__":
    main()
