"""Stage Analysis v2 — Industry ranks engine (SGA-2, masterplan §2.2).

Computes per-GICS-industry momentum ranks from OUR stage output (per-name RS /
stage records), calibrated against EquityDesk's
`stageanalysis_industry_ranks_weekly` (backfill:
`data/stage_analysis/backfill/industry_ranks.parquet`).

Per-industry outputs (mirroring their column semantics):
    industry_id, industry_name, region, n,
    z_rsroc  — RS rate-of-change z (cross-sectional, per region),
    z_mom    — RS-level momentum z (cross-sectional, per region),
    score    — 0.51*z_rsroc + 0.30*z_mom (regression-fit blend vs their score),
    rank     — argsort(score desc), 1-based,
    bucket   — quartile-by-rank {Leading, Improving, Weakening, Lagging},
    industry_percentile — 100*(n_ind-rank)/(n_ind-1).

The per-INDUSTRY `industry_percentile` here is the industry's own momentum
percentile.  The per-NAME `industry_percentile` (the field the stage-v2 name
table consumes, "how strong is this name inside its GICS industry") is computed
separately by :func:`name_industry_percentiles` from member RS ranks and written
to ``data/stage_analysis/industry_name_pctile.json`` for the stage lane to read.

DISPLAY-TIER / CONTEXT-ONLY: nothing here gates, ranks-for-sizing, or sizes a
trade — these are rotation-context signals.  Every input is fail-open: a missing
stage frame, an empty region, or an unreadable parquet yields an empty result,
never a crash.

Calibration HONESTY (MEASURED on the backfill snapshot; see
tests/test_stage_industry.py::test_calibration_smoke and ::test_calibration_floors):
  - rank Spearman ≈ 0.36 (USA) / 0.49 (EUR) / 0.43 (ASIA).  This is NOT an
    independent from-our-OHLCV RS reconstruction: it is OUR AGGREGATION of the
    seed's OWN Mansfield RS + its rate-of-change.  So the honest claim is
    "our aggregation of their RS reproduces their ranks at rho ~0.4"; a genuine
    from-our-OHLCV RS reconstruction is FUTURE WORK.
  - quartile-by-rank `bucket` agreement with their industry_bucket is ~35% —
    NOT the previously-claimed ~99%.  Rank ordering is only weakly reproduced
    (rho ~0.4), and bucket edges compound that, so a third of buckets match.
    Reported honestly, floored in the calibration test so it cannot silently
    drift further.
Their exact z_rsroc RS-window is not exposed; ordinal (rank) agreement — not
exact score parity or bucket parity — is the yardstick.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_ENGINE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _ENGINE_DIR.parent

# Score blend coefficients. Fit against EquityDesk industry_ranks.score using
# THEIR OWN z columns (that in-sample fit is near-perfect precisely because it
# regresses their score on their own z's — a coefficient-recovery check, not a
# fidelity claim); we then reuse those coefficients on OUR reconstructed z's,
# where the real (and only meaningful) yardstick is rank rho ~0.4 above.
W_RSROC = 0.51
W_MOM = 0.30

BUCKET_LABELS = ("Leading", "Improving", "Weakening", "Lagging")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def _data_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    env = os.environ.get("MACRO_DATA_ROOT")
    if env:
        return Path(env)
    return _REPO_ROOT / "data"


# ---------------------------------------------------------------------------
# Stage frame loading (our stage output; backfill seed as fail-open fallback)
# ---------------------------------------------------------------------------
# Columns a stage frame must carry for this engine.  A caller (nightly builder)
# may pass a richer frame straight from the classifier; if none is supplied we
# seed from the committed backfill so the artifact is never blank on a cold
# render.  Reference identity (GICS taxonomy) always comes from the yardstick.
_REQUIRED_COLS = (
    "ticker", "region", "industry_id", "industry_name",
    "mansfield_rs", "mansfield_rs_change",
)


def _seed_stage_frame(dr: Path):
    """Fail-open seed frame from the committed backfill stage snapshot."""
    import pandas as pd

    p = dr / "stage_analysis" / "backfill" / "stage_daily.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("stage_industry: seed frame unreadable (%s)", e)
        return None
    return df


def _coerce_frame(stage_frame, dr: Path):
    """Return a validated DataFrame or None (fail-open)."""
    import pandas as pd

    df = stage_frame
    if df is None:
        df = _seed_stage_frame(dr)
    if df is None:
        return None
    if not isinstance(df, pd.DataFrame):
        try:
            df = pd.DataFrame(df)
        except Exception:  # noqa: BLE001
            return None
    if df.empty:
        return None
    missing = [c for c in _REQUIRED_COLS if c not in df.columns]
    if missing:
        log.warning("stage_industry: stage frame missing %s", missing)
        return None
    out = df[list(_REQUIRED_COLS)].copy()
    # Drop rows with a null industry_id BEFORE the str-cast: astype(str) turns
    # NaN into the literal "nan", which would otherwise group into a spurious
    # 'nan' industry bucket (the seed carries ~31 such rows).
    out = out[out["industry_id"].notna()]
    out["industry_id"] = out["industry_id"].astype(str)
    out = out[out["industry_id"].str.strip().str.lower() != "nan"]
    if out.empty:
        return None
    for c in ("mansfield_rs", "mansfield_rs_change"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


# ---------------------------------------------------------------------------
# Core math
# ---------------------------------------------------------------------------
def _zscore(series):
    """Cross-sectional z-score; zero-variance -> all zeros (fail-open)."""
    import numpy as np

    vals = series.astype(float)
    mu = vals.mean()
    sd = vals.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return vals * 0.0
    return (vals - mu) / sd


def _bucket_by_rank(rank: int, n: int) -> str:
    """Quartile-by-rank label. MEASURED agreement with their industry_bucket is
    ~35% on the backfill (NOT ~99%) — rank ordering reproduces at rho ~0.4 and
    quartile edges compound that. See ::test_calibration_floors."""
    if n <= 0:
        return BUCKET_LABELS[0]
    # position in [0,1): 0 = strongest
    frac = (rank - 1) / n
    if frac < 0.25:
        return "Leading"
    if frac < 0.50:
        return "Improving"
    if frac < 0.75:
        return "Weakening"
    return "Lagging"


def _rank_region(members, region: str):
    """Rank the industries within one region. Returns a list[dict]."""
    import numpy as np

    # per-industry aggregation: RS rate-of-change (rsroc) and RS level (mom)
    g = members.groupby(["industry_id", "industry_name"], as_index=False).agg(
        rsroc=("mansfield_rs_change", "mean"),
        mom=("mansfield_rs", "mean"),
        n=("ticker", "size"),
    )
    if g.empty:
        return []
    g["rsroc"] = g["rsroc"].fillna(0.0)
    g["mom"] = g["mom"].fillna(0.0)
    g["z_rsroc"] = _zscore(g["rsroc"])
    g["z_mom"] = _zscore(g["mom"])
    g["score"] = W_RSROC * g["z_rsroc"] + W_MOM * g["z_mom"]

    g = g.sort_values(["score", "industry_id"], ascending=[False, True]).reset_index(drop=True)
    n_ind = len(g)
    rows: list[dict] = []
    for i, r in g.iterrows():
        rank = int(i) + 1
        pctile = 100.0 * (n_ind - rank) / (n_ind - 1) if n_ind > 1 else 100.0
        rows.append({
            "industry_id": str(r["industry_id"]),
            "industry_name": str(r["industry_name"]),
            "region": region,
            "n": int(r["n"]),
            "z_rsroc": round(float(r["z_rsroc"]), 4),
            "z_mom": round(float(r["z_mom"]), 4),
            "score": round(float(r["score"]), 4),
            "rank": rank,
            "bucket": _bucket_by_rank(rank, n_ind),
            "industry_percentile": round(float(pctile), 1),
        })
    return rows


def ranks(region: str | None = None, stage_frame=None,
          root: Path | None = None) -> list[dict]:
    """Per-GICS-industry momentum ranks.

    Args:
        region: one region ("USA"/"EUROPE"/"ASIA") or None for all regions.
        stage_frame: our per-name stage DataFrame (see _REQUIRED_COLS). When
            None, seeds fail-open from the committed backfill snapshot.
        root: data-root override (tests).

    Returns a list of per-industry rank dicts (schema in module docstring).
    Fail-open: any error or empty input -> [].
    """
    dr = _data_root(root)
    df = _coerce_frame(stage_frame, dr)
    if df is None:
        return []

    if region is not None:
        df = df[df["region"] == region]
        if df.empty:
            return []
        regions = [region]
    else:
        regions = [r for r in df["region"].dropna().unique()]

    out: list[dict] = []
    for reg in regions:
        members = df[df["region"] == reg]
        if members.empty:
            continue
        try:
            out.extend(_rank_region(members, str(reg)))
        except Exception as e:  # noqa: BLE001 — one bad region never breaks the rest
            log.warning("stage_industry: rank_region(%s) failed (%s)", reg, e)
    return out


# ---------------------------------------------------------------------------
# Per-NAME industry percentile (the field the stage-v2 name table consumes)
# ---------------------------------------------------------------------------
def name_industry_percentiles(stage_frame=None, root: Path | None = None) -> dict[str, float]:
    """Per-name percentile of RS strength within the name's own GICS industry.

    Ranks each name against its industry peers (higher Mansfield RS = higher
    percentile).  This is the "Ind %ile" column the stage-v2 name table shows —
    "how strong is this name inside its industry".  Returns {ticker: pct 0..100}.
    Fail-open -> {}.
    """
    import numpy as np

    dr = _data_root(root)
    df = _coerce_frame(stage_frame, dr)
    if df is None:
        return {}
    out: dict[str, float] = {}
    try:
        for (_reg, _ind), grp in df.groupby(["region", "industry_id"]):
            g = grp.dropna(subset=["mansfield_rs"])
            m = len(g)
            if m == 0:
                continue
            if m == 1:
                out[str(g.iloc[0]["ticker"])] = 100.0
                continue
            # average rank (ties share the mid rank) -> percentile
            order = g["mansfield_rs"].rank(method="average", ascending=True)
            for tk, rk in zip(g["ticker"], order):
                pct = 100.0 * (rk - 1) / (m - 1)
                out[str(tk)] = round(float(pct), 1)
    except Exception as e:  # noqa: BLE001
        log.warning("stage_industry: name percentiles failed (%s)", e)
        return {}
    return out


# ---------------------------------------------------------------------------
# Industry rank HEATMAP (weekly rank-over-time grid, per region)
# ---------------------------------------------------------------------------
# Consumed by the Industries surface as a rank-over-time heatmap: rows are GICS
# industries, columns are trailing Friday weeks (most-recent first), cells are
# the industry's rank that week (1 = strongest). Source is the committed
# EquityDesk seed ``industry_ranks.parquet`` (weekly Mansfield-RS ranks, our
# only multi-week rank history) — the live ``ranks()`` above only produces the
# CURRENT week from a stage frame, so the heatmap reads history straight from
# the seed. DISPLAY-TIER / CONTEXT-ONLY: never a signal or a sizing input.

_HEATMAP_WEEKS = 26           # trailing Friday columns
_HEATMAP_MAX_ROWS = 90        # cap industries/region (well under the 1.2MB budget)
_HEATMAP_REGIONS = ("USA", "EUROPE", "ASIA")


def _ranks_seed_path(dr: Path) -> Path:
    return dr / "stage_analysis" / "backfill" / "industry_ranks.parquet"


def industry_heatmap(root: Path | None = None,
                     *, weeks: int = _HEATMAP_WEEKS,
                     max_rows: int = _HEATMAP_MAX_ROWS) -> dict:
    """Per-region rank-over-time grid from the EquityDesk ranks seed.

    Returns {region: {weeks:[Friday dates, most-recent first],
                      rows:[{industry, industry_id, ranks:[rank|null per week]}],
                      n_industries, n_weeks}}. Rows are ordered by the
    most-recent week's rank (strongest first); ``ranks[]`` is aligned to
    ``weeks[]`` with ``null`` where an industry has no rank that week. Fail-open:
    a missing/unreadable seed yields {} (caller renders an empty state).
    """
    import pandas as pd  # noqa: PLC0415

    dr = _data_root(root)
    p = _ranks_seed_path(dr)
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(
            p, columns=["region", "industry_id", "industry_name",
                        "as_of_date", "rank"])
    except Exception as e:  # noqa: BLE001
        log.warning("stage_industry: heatmap seed unreadable (%s)", e)
        return {}
    if df.empty:
        return {}

    out: dict[str, dict] = {}
    try:
        dates = pd.to_datetime(df["as_of_date"], errors="coerce")
        df = df.assign(dt_=dates)
        # Restrict to week-ending Fridays (their as_of convention); the seed is
        # daily, so a Friday filter yields the clean weekly grid the page draws.
        fri = df[df["dt_"].dt.weekday == 4]
        if fri.empty:
            return {}
        for reg in _HEATMAP_REGIONS:
            sub = fri[fri["region"] == reg]
            if sub.empty:
                continue
            grid = _heatmap_region(sub, weeks=weeks, max_rows=max_rows)
            if grid is not None:
                out[reg] = grid
    except Exception as e:  # noqa: BLE001 — one bad region never sinks the rest
        log.warning("stage_industry: heatmap build failed (%s)", e)
    return out


def _heatmap_region(sub, *, weeks: int, max_rows: int) -> dict | None:
    """Build one region's grid. `sub` = Friday rows for a single region."""
    import pandas as pd  # noqa: PLC0415

    # Trailing `weeks` Friday columns, most-recent first.
    all_weeks = sorted(sub["dt_"].dropna().unique())
    if not all_weeks:
        return None
    keep = all_weeks[-weeks:]
    week_labels = [pd.Timestamp(w).date().isoformat() for w in reversed(keep)]
    keep_set = set(keep)
    win = sub[sub["dt_"].isin(keep_set)]

    # rank per (industry_id, week) — dedupe to one row per cell (last wins).
    win = win.sort_values("dt_")
    name_by_id: dict[str, str] = {}
    ranks_by_id: dict[str, dict] = {}
    for row in win.itertuples():
        iid = str(row.industry_id)
        if iid in ("", "nan", "None"):
            continue
        wk = pd.Timestamp(row.dt_).date().isoformat()
        try:
            rk = int(row.rank)
        except (TypeError, ValueError):
            continue
        ranks_by_id.setdefault(iid, {})[wk] = rk
        name_by_id[iid] = str(row.industry_name)

    if not ranks_by_id:
        return None

    # Order rows by the most-recent week's rank (strongest first); industries
    # absent in the latest week fall to the bottom, then by best rank seen.
    latest = week_labels[0]

    def _sort_key(iid: str):
        rk = ranks_by_id[iid].get(latest)
        if rk is not None:
            return (0, rk)
        best = min(ranks_by_id[iid].values())
        return (1, best)

    ordered = sorted(ranks_by_id.keys(), key=_sort_key)[:max_rows]
    rows = [{
        "industry": name_by_id[iid],
        "industry_id": iid,
        "ranks": [ranks_by_id[iid].get(wk) for wk in week_labels],
    } for iid in ordered]

    return {
        "weeks": week_labels,
        "rows": rows,
        "n_industries": len(rows),
        "n_weeks": len(week_labels),
    }


def build_industry_heatmap(root: Path | None = None,
                           asof: str | None = None) -> dict:
    """Compute the per-region rank heatmap and write the display-tier artifact.

    Writes ``data/stage_analysis/industry_heatmap.json``. Fail-open throughout.
    """
    dr = _data_root(root)
    if asof is None:
        asof = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    regions = industry_heatmap(root=root)
    contract = {
        "schema": "stage_industry_heatmap.v1",
        "asof": asof,
        "built": built,
        "is_context_only": True,
        "display_only": True,
        "disclaimer": ("Context only — industry rank-over-time for rotation "
                       "display, never a signal or sizing input."),
        "source": "stageanalysis_industry_ranks_weekly (EquityDesk seed)",
        "note": ("cell = industry rank that Friday week (1 = strongest); "
                 "weeks most-recent-first; null = no rank that week"),
        "regions": regions,
        "n_regions": len(regions),
    }
    try:
        _atomic_write_json(dr / "stage_analysis" / "industry_heatmap.json", contract)
    except Exception as e:  # noqa: BLE001 — write failure never breaks a build
        log.warning("::warning:: stage_industry: failed to write heatmap (%s)", e)
    return contract


# ---------------------------------------------------------------------------
# Artifact emission
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, obj: Any) -> None:
    """Temp-file + os.replace atomic write (house law)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def build(stage_frame=None, root: Path | None = None,
          asof: str | None = None) -> dict:
    """Compute ranks for all regions, write display-tier artifacts, return the
    contract.  Fail-open throughout.

    Writes:
        data/stage_analysis/industry_ranks.json  (industry-level ranks)
        data/stage_analysis/industry_name_pctile.json  (per-name Ind %ile)
        data/stage_analysis/industry_heatmap.json  (rank-over-time grid)
    """
    dr = _data_root(root)
    if asof is None:
        asof = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Coerce once so both artifacts share the same source frame.
    df = _coerce_frame(stage_frame, dr)
    all_ranks = ranks(region=None, stage_frame=df, root=root) if df is not None else []
    name_pct = name_industry_percentiles(stage_frame=df, root=root) if df is not None else {}

    by_region: dict[str, list] = {}
    for r in all_ranks:
        by_region.setdefault(r["region"], []).append(r)

    contract = {
        "schema": "stage_industry_ranks.v1",
        "asof": asof,
        "built": built,
        "is_context_only": True,
        "display_only": True,
        "disclaimer": ("Context only — industry momentum ranks for rotation "
                       "display, never a signal or sizing input."),
        "calibration": {
            "target": "stageanalysis_industry_ranks_weekly (EquityDesk)",
            "method": ("our aggregation of THEIR Mansfield RS + rate-of-change "
                       "(not a from-our-OHLCV RS reconstruction — that is future "
                       "work)"),
            "note": ("rank rho ~0.4 (USA .36 / EUR .49 / ASIA .43); "
                     "quartile-bucket agreement ~35% — measured, ordinal only"),
        },
        # FIX 3 — ranks / percentiles are computed WITHIN each region's own
        # cross-section (the `score` is a per-region z-score, so a 1.2 in Asia is
        # NOT comparable to a 1.2 in USA in absolute RS terms). Concatenating the
        # three region lists for an "All" view therefore yields THREE rank-1 /
        # percentile-100 rows — one per region — which reads as duplicate leaders.
        # We do NOT fabricate a cross-region global rank from non-comparable
        # z-scores (that would be a statistically invalid comparison). Instead we
        # tag every row with its `region` (already present) and flag the concat so
        # the Industries surface defaults to a single region (N.America) or adds a
        # Region column rather than showing a merged, misleading "All".
        "all_region_is_concat": True,
        "all_region_note": (
            "Ranks and percentiles are region-relative (per-region z-scores). An "
            "'All' view is a concatenation of the three per-region lists, so it "
            "carries one rank-1 / percentile-100 row PER region — not a global "
            "ranking. Default the surface to one region (N.America) or show a "
            "Region column; a true cross-region global rank is not computed "
            "because the per-region scores are not comparable across regions."
        ),
        "regions": {reg: sorted(rows, key=lambda x: x["rank"])
                    for reg, rows in by_region.items()},
        "n_regions": len(by_region),
        "n_industries": len(all_ranks),
    }
    try:
        _atomic_write_json(dr / "stage_analysis" / "industry_ranks.json", contract)
    except Exception as e:  # noqa: BLE001 — write failure never breaks a build
        log.warning("::warning:: stage_industry: failed to write ranks (%s)", e)

    try:
        _atomic_write_json(
            dr / "stage_analysis" / "industry_name_pctile.json",
            {"schema": "stage_industry_name_pctile.v1", "asof": asof,
             "built": built, "is_context_only": True, "display_only": True,
             "percentiles": name_pct},
        )
    except Exception as e:  # noqa: BLE001
        log.warning("::warning:: stage_industry: failed to write name pctile (%s)", e)

    # Rank-over-time heatmap grid (reads the weekly ranks seed directly, so it
    # runs independent of the stage frame). Fail-open — never breaks the build.
    try:
        build_industry_heatmap(root=root, asof=asof)
    except Exception as e:  # noqa: BLE001
        log.warning("::warning:: stage_industry: failed to write heatmap (%s)", e)

    return contract
