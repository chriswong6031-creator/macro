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

# A live build must cover a meaningful share of the classified universe and
# carry an actual RS-change observation.  These are observability guards, not
# trading gates: degraded builds still publish fail-open artifacts, but their
# contract status is ``warn`` instead of silently presenting an empty surface
# as healthy.
MIN_TAXONOMY_COVERAGE_PCT = 50.0
MIN_RS_CHANGE_COVERAGE_PCT = 25.0


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


def _normalise_region(value: Any) -> str | None:
    """Map source-region aliases onto the three Stage surface regions."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    key = text.lower().replace(".", "").replace("_", " ").strip()
    if key in {"usa", "us", "north america", "n amer", "namer", "namerica"}:
        return "USA"
    if key in {"europe", "european", "eu"}:
        return "EUROPE"
    if key in {"asia", "asian", "apac"}:
        return "ASIA"
    return text.upper()


def _load_gics_map(dr: Path):
    """Reference-only ticker taxonomy from the committed overview yardstick.

    Stage/RS values from the overview are deliberately ignored.  The live
    classifier remains the sole source for stage, RS, SATA, and freshness.
    """
    import pandas as pd

    p = dr / "stage_analysis" / "backfill" / "equitydesk_overview.parquet"
    if not p.exists():
        return None
    try:
        ov = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("stage_industry: overview GICS map unreadable (%s)", e)
        return None
    if ov.empty or "ticker" not in ov.columns or "gics_industry" not in ov.columns:
        return None
    keep = [c for c in ("ticker", "region", "gics_industry", "gics_sub_industry")
            if c in ov.columns]
    ov = ov[keep].copy()
    ov["ticker"] = ov["ticker"].astype(str).str.split().str[0].str.upper()
    if "region" in ov.columns:
        ov["region"] = ov["region"].map(_normalise_region)
    return ov.drop_duplicates(subset=["ticker"], keep="last")


def prepare_live_frame(stage_frame, root: Path | None = None,
                       source_asof: str | None = None):
    """Normalise one live classifier frame for ranks *and* flows.

    The live Stage records carry current classifier values but intentionally do
    not depend on the stale overview's stage fields.  This adapter joins only
    reference GICS identity, maps ``stage`` to ``stage_flag``, derives the
    fresh-Stage-2 marker, and stamps the classifier as-of supplied by the
    orchestrator.  The returned richer frame is shared by both side engines so
    ranks, per-name percentiles, flows, and the screener cannot drift onto
    different snapshots.
    """
    import pandas as pd

    if stage_frame is None:
        return None
    if isinstance(stage_frame, pd.DataFrame):
        out = stage_frame.copy()
    else:
        try:
            out = pd.DataFrame(stage_frame)
        except Exception:  # noqa: BLE001
            return None
    if out.empty or "ticker" not in out.columns:
        return out

    out["ticker"] = out["ticker"].astype(str).str.split().str[0].str.upper()
    if "stage_flag" not in out.columns and "stage" in out.columns:
        out["stage_flag"] = pd.to_numeric(out["stage"], errors="coerce")
    if "is_stage2_start" not in out.columns:
        stage_values = pd.to_numeric(
            out.get("stage_flag", out.get("stage")), errors="coerce",
        )
        weeks_values = pd.to_numeric(out.get("weeks_in_stage"), errors="coerce")
        if stage_values is not None and weeks_values is not None:
            out["is_stage2_start"] = (stage_values == 2) & (weeks_values == 1)
        else:
            out["is_stage2_start"] = False
    if "mansfield_rs_change" not in out.columns:
        out["mansfield_rs_change"] = float("nan")

    # Seed the canonical columns before fill-map operations.
    if "region" not in out.columns:
        out["region"] = None
    if "industry_id" not in out.columns:
        out["industry_id"] = None
    if "industry_name" not in out.columns:
        out["industry_name"] = out.get("industry")
    if "sub_industry_id" not in out.columns:
        out["sub_industry_id"] = None
    if "sub_industry_name" not in out.columns:
        out["sub_industry_name"] = None

    gics = _load_gics_map(_data_root(root))
    if gics is not None:
        gmap = gics.set_index("ticker")

        def _fill(column: str, source: str) -> None:
            if source not in gmap.columns:
                return
            mapped = out["ticker"].map(gmap[source])
            cur = out[column]
            missing = cur.isna() | cur.astype(str).str.strip().str.lower().isin(
                {"", "nan", "none"})
            out.loc[missing, column] = mapped.loc[missing]

        _fill("region", "region")
        _fill("industry_id", "gics_industry")
        _fill("industry_name", "gics_industry")
        _fill("sub_industry_id", "gics_sub_industry")
        _fill("sub_industry_name", "gics_sub_industry")

    out["region"] = out["region"].map(_normalise_region)
    # If the yardstick lacks a sub-industry, preserve a usable parent fallback.
    for sub_col, parent_col in (("sub_industry_id", "industry_id"),
                                ("sub_industry_name", "industry_name")):
        missing = out[sub_col].isna() | out[sub_col].astype(str).str.strip().str.lower().isin(
            {"", "nan", "none"})
        out.loc[missing, sub_col] = out.loc[missing, parent_col]
    if source_asof is not None:
        out["stage_source_asof"] = str(source_asof)
    return out


def coverage_snapshot(stage_frame, expected_asof: str | None,
                      output_rows: int, *,
                      expected_stage_week: str | None = None) -> dict:
    """Return non-vacuous coverage/freshness diagnostics for an artifact.

    Wave 8 §6.1 — the classifier is weekly-native, so a current Stage week
    must not be downgraded to ``warn`` merely because the UTC build clock
    rolled forward one calendar day. When the caller supplies
    ``expected_stage_week`` (the resolved target Stage week) AND the frame
    itself carries ``stage_week_end`` values, freshness is judged on the
    STAGE-WEEK plane (equality of completed weeks) rather than the daily
    ``expected_asof`` vs ``source_asof`` comparison. The daily values stay in
    the payload for audit either way, but only generate an issue when the
    week plane could not answer (``freshness.plane == "daily"``).
    """
    import pandas as pd

    if stage_frame is None or not isinstance(stage_frame, pd.DataFrame):
        df = pd.DataFrame()
    else:
        df = stage_frame
    input_rows = int(len(df))

    def _valid(col: str):
        if col not in df.columns:
            return pd.Series(False, index=df.index, dtype=bool)
        raw = df[col]
        text = raw.astype(str).str.strip().str.lower()
        return raw.notna() & ~text.isin({"", "nan", "none"})

    taxonomy = _valid("region") & _valid("industry_id")
    rs = pd.to_numeric(df.get("mansfield_rs"), errors="coerce").notna() \
        if "mansfield_rs" in df.columns else pd.Series(False, index=df.index)
    rs_change = pd.to_numeric(df.get("mansfield_rs_change"), errors="coerce").notna() \
        if "mansfield_rs_change" in df.columns else pd.Series(False, index=df.index)
    eligible = taxonomy & rs
    taxonomy_rows = int(taxonomy.sum())
    eligible_rows = int(eligible.sum())
    change_rows = int((eligible & rs_change).sum())
    taxonomy_pct = round(100.0 * taxonomy_rows / input_rows, 1) if input_rows else 0.0
    change_pct = round(100.0 * change_rows / eligible_rows, 1) if eligible_rows else 0.0

    source_asof = None
    for col in ("stage_source_asof", "data_as_of_date", "week_end", "date"):
        if col not in df.columns:
            continue
        parsed = pd.to_datetime(df[col], errors="coerce", utc=True).dropna()
        if not parsed.empty:
            source_asof = parsed.max().date().isoformat()
            break
    if source_asof is None or expected_asof is None:
        daily_freshness = "unknown"
    elif source_asof == str(expected_asof):
        daily_freshness = "current"
    elif source_asof < str(expected_asof):
        daily_freshness = "stale"
    else:
        daily_freshness = "future"

    # Wave 8 §6.1 — the STAGE-WEEK plane. `source_stage_week` = max of the
    # frame's own `stage_week_end` values (the completed week the classifier
    # actually read). When both it and the resolved target week exist, that
    # is the authoritative freshness plane; the wall-clock-driven daily
    # comparison above is audit-only in that case.
    source_stage_week = None
    if "stage_week_end" in df.columns:
        raw = df["stage_week_end"].dropna().astype(str).str.strip()
        raw = raw[~raw.str.lower().isin({"", "nan", "none"})]
        if not raw.empty:
            source_stage_week = str(raw.max())

    if expected_stage_week is not None and source_stage_week is not None:
        plane = "stage_week"
        if source_stage_week == str(expected_stage_week):
            week_freshness = "current"
        elif source_stage_week < str(expected_stage_week):
            week_freshness = "stale"
        else:
            week_freshness = "future"
        freshness = week_freshness
    else:
        plane = "daily"
        freshness = daily_freshness

    non_vacuous = eligible_rows > 0 and int(output_rows) > 0
    issues: list[str] = []
    if input_rows == 0:
        issues.append("no_input_rows")
    if eligible_rows == 0:
        issues.append("no_eligible_rows")
    if int(output_rows) == 0:
        issues.append("no_output_rows")
    if input_rows and taxonomy_pct < MIN_TAXONOMY_COVERAGE_PCT:
        issues.append("taxonomy_coverage_below_floor")
    if eligible_rows and change_pct < MIN_RS_CHANGE_COVERAGE_PCT:
        issues.append("rs_change_coverage_below_floor")
    # The daily-plane issue must NEVER fire once the week plane has answered
    # (§6.1) — a settled daily tape behind a rolled UTC calendar is not
    # staleness when the Stage week itself is current.
    if plane == "daily":
        if freshness != "current":
            issues.append(f"source_asof_{freshness}")
    else:
        if freshness != "current":
            issues.append(f"source_stage_week_{freshness}")

    regions = sorted(str(v) for v in df.loc[taxonomy, "region"].dropna().unique()) \
        if "region" in df.columns else []
    return {
        "status": "ready" if non_vacuous and not issues else "warn",
        "non_vacuous": non_vacuous,
        "input_rows": input_rows,
        "taxonomy_rows": taxonomy_rows,
        "taxonomy_coverage_pct": taxonomy_pct,
        "eligible_rows": eligible_rows,
        "rs_change_rows": change_rows,
        "rs_change_coverage_pct": change_pct,
        "output_rows": int(output_rows),
        "regions": regions,
        "freshness": {
            "expected_asof": expected_asof,
            "source_asof": source_asof,
            "status": freshness,
            "plane": plane,
            "expected_stage_week": expected_stage_week,
            "source_stage_week": source_stage_week,
        },
        "floors": {
            "taxonomy_coverage_pct": MIN_TAXONOMY_COVERAGE_PCT,
            "rs_change_coverage_pct": MIN_RS_CHANGE_COVERAGE_PCT,
        },
        "issues": issues,
    }


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
    if any(c not in df.columns for c in _REQUIRED_COLS):
        df = prepare_live_frame(df, root=dr)
        if df is None or df.empty:
            return None
    missing = [c for c in _REQUIRED_COLS if c not in df.columns]
    if missing:
        log.warning("stage_industry: stage frame missing %s", missing)
        return None
    keep = list(_REQUIRED_COLS) + [
        c for c in ("stage_source_asof", "data_as_of_date", "week_end", "date")
        if c in df.columns
    ]
    out = df[keep].copy()
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
# Industry rank HISTORY — house-native weekly accrual (Wave 8 §7)
# ---------------------------------------------------------------------------
# The heatmap below used to read a one-shot proprietary EquityDesk export
# (`data/stage_analysis/backfill/industry_ranks.parquet`) that is ABSENT from
# the committed backfill — the heatmap was structurally dead (`regions: []`).
# We do NOT re-import that seed as an ongoing production dependency. Instead
# this nightly Stage lane accrues its OWN weekly history, one record per
# (stage_week_end, region, industry_id), following the house JSONL idiom
# `engine/stage_analysis.py::append_forward_ledger`: keyed on a DATA-plane
# date (the Stage week), never a clock read; deduped; fail-open; disclosing
# skips via `::warning`. Past weeks are IMMUTABLE — only the target week's
# record set may ever be dropped or rewritten (a same-week rerun replaces
# that week's point, which is also the deterministic correction path for a
# corrected OHLCV file). DISPLAY-TIER / CONTEXT-ONLY throughout.

_HISTORY_FIELDS = ("industry_id", "industry_name", "region", "n", "score",
                   "rank", "bucket", "industry_percentile")
_HISTORY_KEEP_WEEKS = 30       # newest 30 distinct stage_week_end values


def _history_path(dr: Path) -> Path:
    return dr / "stage_analysis" / "industry_rank_history.jsonl"


def _read_history(dr: Path) -> list[dict]:
    """Read all history records. Fail-open -> []; malformed lines are skipped."""
    p = _history_path(dr)
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        raw = p.read_text()
    except Exception as e:  # noqa: BLE001
        log.warning("stage_industry: history unreadable (%s)", e)
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001 — one bad line never sinks the rest
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _atomic_write_jsonl(path: Path, records: list[dict]) -> None:
    """Temp-file + os.replace atomic whole-file rewrite (house law)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    lines = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records]
    tmp.write_text("\n".join(lines) + ("\n" if lines else ""))
    os.replace(tmp, path)


def append_industry_rank_history(all_ranks: list[dict], stage_week_end: str | None,
                                 coverage: dict | None,
                                 root: Path | None = None) -> dict:
    """Accrue one house-native weekly point per (stage_week_end, region,
    industry_id) into ``data/stage_analysis/industry_rank_history.jsonl``.

    Advances ONLY when all of (§7.3):
      - `stage_week_end` is not None;
      - `coverage["non_vacuous"] is True`;
      - `coverage["status"] == "ready"` (which already implies no currentness
        issue — `coverage_snapshot` only reports "ready" when `issues` is
        empty).

    Otherwise: skip and warn naming exactly why; the prior history stands.
    Idempotent: a rebuild for the SAME target week REPLACES that week's
    records (drop-then-append), never duplicates them. Past weeks are never
    touched except by the retention trim (newest `_HISTORY_KEEP_WEEKS`
    distinct weeks). Never advances from a wall-clock date, never
    synthesizes, never re-imports the seed.
    """
    dr = _data_root(root)
    coverage = coverage or {}

    reasons: list[str] = []
    if stage_week_end is None:
        reasons.append("no_target_stage_week")
    if coverage.get("non_vacuous") is not True:
        reasons.append("not_non_vacuous")
    if coverage.get("status") != "ready":
        reasons.append("coverage_not_ready")
    if reasons:
        print("::warning title=industry-rank-history::stage_industry: history "
              f"NOT advanced ({','.join(reasons)})", flush=True)
        return {"advanced": False, "reason": ",".join(reasons), "week": stage_week_end}

    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_records: list[dict] = []
    for r in all_ranks:
        rec = {"stage_week_end": stage_week_end}
        for f in _HISTORY_FIELDS:
            rec[f] = r.get(f)
        rec["built"] = built
        rec["source"] = "stage_industry.live"
        new_records.append(rec)

    existing = _read_history(dr)
    # Idempotent replace: drop every record for the target week, then append
    # the freshly computed set — a same-week rebuild REPLACES the point.
    kept = [r for r in existing if r.get("stage_week_end") != stage_week_end]
    merged = kept + new_records

    weeks = sorted({str(r["stage_week_end"]) for r in merged if r.get("stage_week_end")})
    if len(weeks) > _HISTORY_KEEP_WEEKS:
        keep_weeks = set(weeks[-_HISTORY_KEEP_WEEKS:])
        merged = [r for r in merged if str(r.get("stage_week_end")) in keep_weeks]

    merged.sort(key=lambda r: (
        str(r.get("stage_week_end")), str(r.get("region")),
        r.get("rank") if r.get("rank") is not None else 0,
    ))

    try:
        _atomic_write_jsonl(_history_path(dr), merged)
    except Exception as e:  # noqa: BLE001 — write failure never breaks a build
        print(f"::warning title=industry-rank-history::stage_industry: failed to "
              f"write history ({e})", flush=True)
        return {"advanced": False, "reason": "write_failed", "week": stage_week_end}

    return {"advanced": True, "reason": None, "week": stage_week_end,
            "n_records": len(new_records), "n_total": len(merged)}


# ---------------------------------------------------------------------------
# Industry rank HEATMAP (weekly rank-over-time grid, per region)
# ---------------------------------------------------------------------------
# Consumed by the Industries surface as a rank-over-time heatmap: rows are GICS
# industries, columns are trailing Stage weeks (most-recent first), cells are
# the industry's rank that week (1 = strongest). Source is the house-native
# `industry_rank_history.jsonl` above — the live ``ranks()`` function only
# produces the CURRENT week from a stage frame, so the heatmap reads
# multi-week history straight from the accrual store. DISPLAY-TIER /
# CONTEXT-ONLY: never a signal or a sizing input.

_HEATMAP_WEEKS = 26           # trailing Stage-week columns
_HEATMAP_MAX_ROWS = 90        # cap industries/region (well under the 1.2MB budget)
_HEATMAP_REGIONS = ("USA", "EUROPE", "ASIA")


def industry_heatmap(root: Path | None = None,
                     *, weeks: int = _HEATMAP_WEEKS,
                     max_rows: int = _HEATMAP_MAX_ROWS) -> dict:
    """Per-region rank-over-time grid from the house-native rank history.

    Returns {region: {weeks:[Stage-week dates, most-recent first],
                      rows:[{industry, industry_id, ranks:[rank|null per week]}],
                      n_industries, n_weeks}}. Rows are ordered by the
    most-recent week's rank (strongest first); ``ranks[]`` is aligned to
    ``weeks[]`` with ``null`` where an industry has no rank that week. Fail-open:
    an absent/empty history yields {} (caller renders an explicit
    accruing/unavailable state, never a healthy-looking blank panel).
    """
    dr = _data_root(root)
    records = _read_history(dr)
    if not records:
        return {}

    out: dict[str, dict] = {}
    try:
        for reg in _HEATMAP_REGIONS:
            sub = [r for r in records if r.get("region") == reg]
            if not sub:
                continue
            grid = _heatmap_region_from_history(sub, weeks=weeks, max_rows=max_rows)
            if grid is not None:
                out[reg] = grid
    except Exception as e:  # noqa: BLE001 — one bad region never sinks the rest
        log.warning("stage_industry: heatmap build failed (%s)", e)
    return out


def _heatmap_region_from_history(sub: list[dict], *, weeks: int,
                                 max_rows: int) -> dict | None:
    """Build one region's grid. `sub` = history records for a single region."""
    all_weeks = sorted({str(r["stage_week_end"]) for r in sub
                        if r.get("stage_week_end")})
    if not all_weeks:
        return None
    keep = all_weeks[-weeks:]
    week_labels = list(reversed(keep))
    keep_set = set(keep)

    name_by_id: dict[str, str] = {}
    ranks_by_id: dict[str, dict] = {}
    for r in sub:
        wk = str(r.get("stage_week_end") or "")
        if wk not in keep_set:
            continue
        iid = str(r.get("industry_id") or "")
        if iid in ("", "nan", "None"):
            continue
        try:
            rk = int(r["rank"])
        except (TypeError, ValueError, KeyError):
            continue
        ranks_by_id.setdefault(iid, {})[wk] = rk
        name_by_id[iid] = str(r.get("industry_name") or iid)

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


def _history_status_block(dr: Path) -> dict:
    """§7.4 — honest accrual status for the heatmap contract.

    `unavailable` = 0 distinct weeks; `accruing` = 1-25; `ready` = 26+. The
    client must never render a blank panel that reads as healthy, and must
    never fabricate 26 weeks — on first deployment the truthful render is one
    real column.
    """
    records = _read_history(dr)
    distinct_weeks = sorted({str(r["stage_week_end"]) for r in records
                             if r.get("stage_week_end")})
    n_weeks = len(distinct_weeks)
    if n_weeks == 0:
        status = "unavailable"
    elif n_weeks < _HEATMAP_WEEKS:
        status = "accruing"
    else:
        status = "ready"
    return {
        "status": status,
        "weeks_available": n_weeks,
        "weeks_target": _HEATMAP_WEEKS,
        "first_week": distinct_weeks[0] if distinct_weeks else None,
        "latest_week": distinct_weeks[-1] if distinct_weeks else None,
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
        "source": ("house-native stage industry rank history "
                   "(data/stage_analysis/industry_rank_history.jsonl)"),
        "note": ("cell = industry rank that Stage week (1 = strongest); "
                 "weeks most-recent-first; null = no rank that week"),
        "history": _history_status_block(dr),
        "regions": regions,
        "n_regions": len(regions),
    }
    try:
        _atomic_write_json(dr / "stage_analysis" / "industry_heatmap.json", contract)
    except Exception as e:  # noqa: BLE001 — write failure never breaks a build
        # Bare print, NOT a logger call: GitHub only parses a workflow command when
        # "::" STARTS the line, and this module's logging format prefixes every
        # record (e.g. "WARNING ::warning ..."), which silently drops the annotation.
        print(f"::warning:: stage_industry: failed to write heatmap ({e})", flush=True)
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
          asof: str | None = None,
          target_stage_week: str | None = None) -> dict:
    """Compute ranks for all regions, write display-tier artifacts, return the
    contract.  Fail-open throughout.

    Args:
        target_stage_week: the resolved completed Stage week (Wave 8 §1.2).
            Threaded into `coverage_snapshot` as `expected_stage_week` so
            freshness is judged on the Stage-week plane (§6.1), and into
            `append_industry_rank_history` as the key a healthy build
            advances (§7.3). ``None`` from a caller that has no current
            cross-sectional authority — coverage falls back to the daily
            plane and history does not advance.

    Writes:
        data/stage_analysis/industry_ranks.json  (industry-level ranks)
        data/stage_analysis/industry_name_pctile.json  (per-name Ind %ile)
        data/stage_analysis/industry_heatmap.json  (rank-over-time grid)
        data/stage_analysis/industry_rank_history.jsonl  (weekly accrual, §7)
    """
    dr = _data_root(root)
    if asof is None:
        asof = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Preserve the full prepared input for coverage accounting; _coerce_frame
    # drops unmatched taxonomy rows by design, which must not inflate reported
    # coverage to a fictional 100%.
    source_frame = stage_frame if stage_frame is not None else _seed_stage_frame(dr)
    if source_frame is not None:
        try:
            import pandas as pd  # noqa: PLC0415
            if not isinstance(source_frame, pd.DataFrame):
                source_frame = pd.DataFrame(source_frame)
            if any(c not in source_frame.columns for c in _REQUIRED_COLS):
                source_frame = prepare_live_frame(source_frame, root=dr)
        except Exception:  # noqa: BLE001
            source_frame = None

    # Coerce once so both artifacts share the same source frame.
    df = _coerce_frame(source_frame, dr)
    all_ranks = ranks(region=None, stage_frame=df, root=root) if df is not None else []
    name_pct = name_industry_percentiles(stage_frame=df, root=root) if df is not None else {}

    by_region: dict[str, list] = {}
    for r in all_ranks:
        by_region.setdefault(r["region"], []).append(r)
    coverage = coverage_snapshot(source_frame, expected_asof=asof,
                                 output_rows=len(all_ranks),
                                 expected_stage_week=target_stage_week)

    contract = {
        "schema": "stage_industry_ranks.v1",
        "asof": asof,
        "built": built,
        "status": coverage["status"],
        "coverage": coverage,
        "is_context_only": True,
        "display_only": True,
        "disclaimer": ("Context only — industry momentum ranks for rotation "
                       "display, never a signal or sizing input."),
        # Wave 8 §6.3 — separate WHAT we compute (method, house-native, plane)
        # from WHAT we historically compare it against (calibration, an
        # ordinal yardstick only). The shipping path builds this frame from
        # our own OHLCV classifier records; EquityDesk is never an input.
        "method": {
            "live": ("House-native: Mansfield RS and 4-week RS change computed "
                     "from our own OHLCV via the Weinstein stage classifier, "
                     "grouped by reference GICS taxonomy. Ranks are per-region "
                     "z-scores of the blended score."),
            "plane": "completed W-FRI stage week",
        },
        "calibration": {
            "target": "stageanalysis_industry_ranks_weekly (EquityDesk)",
            "yardstick": ("Historical comparison only — the EquityDesk dataset "
                          "is NOT an input to the shipping calculation."),
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
        print(f"::warning:: stage_industry: failed to write ranks ({e})", flush=True)

    try:
        _atomic_write_json(
            dr / "stage_analysis" / "industry_name_pctile.json",
            {"schema": "stage_industry_name_pctile.v1", "asof": asof,
             "built": built, "status": coverage["status"],
             "coverage": coverage,
             "is_context_only": True, "display_only": True,
             "percentiles": name_pct},
        )
    except Exception as e:  # noqa: BLE001
        print(f"::warning:: stage_industry: failed to write name pctile ({e})", flush=True)

    # Wave 8 §7.3 — house-native weekly history accrual. Advances only on a
    # genuinely healthy, current build (see the function docstring for the
    # exact guard); every other case skips and warns naming why. Must run
    # BEFORE the heatmap rebuild below so a freshly-accrued week is visible
    # in the same build that produced it.
    try:
        append_industry_rank_history(all_ranks, target_stage_week, coverage, root)
    except Exception as e:  # noqa: BLE001 — history accrual never breaks a build
        print(f"::warning title=industry-rank-history::stage_industry: failed to "
              f"append history ({e})", flush=True)

    # Rank-over-time heatmap grid (reads the house-native weekly history, so it
    # runs independent of the stage frame). Fail-open — never breaks the build.
    try:
        build_industry_heatmap(root=root, asof=asof)
    except Exception as e:  # noqa: BLE001
        print(f"::warning:: stage_industry: failed to write heatmap ({e})", flush=True)

    if coverage["status"] != "ready":
        log.warning("stage_industry: degraded live coverage (%s)",
                    ",".join(coverage["issues"]) or "unknown")

    return contract
