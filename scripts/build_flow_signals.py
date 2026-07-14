"""scripts/build_flow_signals.py — nightly flow-signal ledger entrypoint.

Nightly pipeline:
  1. Harvest new events from R2 archive blobs + feed_current (collectors/flow_signals.py)
  2. Grade matured rows (engine/flow_signals_grade.py)
  3. Score new events per bucket (lib/flow_score — lazy import per FS-R7)
  4. Write data/flow_signals/gate.json v2 (status artifact)
  5. Register in data/run_status.json (P0.7 pattern)
  6. Audit tripwire: warn if last harvest is >= 2 trading days stale

Runtime budget: trivial (<60s typical; harvest is bounded by archive blob count × small JSON).

FORWARD-LEDGER LAW: this script is the SOLE ADVANCER of the flow-signal ledger.
  Intraday lanes must not call collectors.flow_signals.harvest() with dry_run=False.

LAZY SKLEARN IMPORT LAW (FS-R7):
  sklearn is NEVER imported at module level. The scoring step lazy-imports
  lib.flow_score INSIDE the step function so this module can be imported without
  sklearn installed (nightly render path).

PRE-GATE LAW (amendment §9 / FS-R3):
  score_calibrated is display-only. Scoring step NEVER blocks or fails the
  harvest/grade/gate pipeline (null never blocks accrual).

Usage:
  python -m scripts.build_flow_signals             # normal nightly run
  python -m scripts.build_flow_signals --dry-run   # no writes (smoke)
  python -m scripts.build_flow_signals --verbose   # debug logging
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# Frozen status enum values (mirrors lib/flow_score.py — kept in sync)
_STATUS_SCORED                 = "scored"
_STATUS_NO_MODEL               = "no_model"
_STATUS_NOT_DEPLOYABLE         = "not_deployable"
_STATUS_PREFILTERED_INDEX_ROOT = "prefiltered_index_root"
_STATUS_BUCKET_UNMAPPED        = "bucket_unmapped"
_STATUS_ERROR                  = "error"

# Known index roots (mirrors ops_train_flow_score.py _INDEX_ROOTS)
_INDEX_ROOTS: frozenset[str] = frozenset([
    "SPX", "SPXW", "NDX", "RUT", "VIX", "VIXW",
    "OEX", "XEO", "DJX", "MNX",
])


# ── gate.json writer ──────────────────────────────────────────────────────────

def _write_gate(
    gate_path: Path,
    ledger_stats: dict,
    grade_summary: dict,
    harvest_n_new: int,
    elapsed_sec: float,
    asof: str,
    scoring_summary: dict | None = None,
) -> None:
    """Write data/flow_signals/gate.json v2 (status artifact).

    Schema bumped to flow_signals.gate/v2 — adds a top-level "scoring" block
    with enabled, model_versions, n_scored_total, n_scored_this_run, by_status,
    calibration per bucket (from manifests), and monitor per bucket (decay sentinel).
    """
    # Events-per-day stats
    epd = ledger_stats.get("events_per_day", {})
    n_by_dte = ledger_stats.get("dte_bucket_counts", {})

    # Compute events/day mean (over last 30 days)
    epd_values = list(epd.values())
    epd_mean = round(sum(epd_values) / len(epd_values), 1) if epd_values else 0.0

    # Build scoring block (from scoring_summary returned by _run_scoring_step)
    if scoring_summary is None:
        scoring_summary = {}
    scoring_block: dict = {
        "enabled": bool(scoring_summary.get("enabled", False)),
        "model_versions": scoring_summary.get("model_versions", {}),
        "n_scored_total": int(scoring_summary.get("n_scored_total", 0)),
        "n_scored_this_run": int(scoring_summary.get("n_scored_this_run", 0)),
        "by_status": scoring_summary.get("by_status", {}),
        "calibration": scoring_summary.get("calibration", {}),
        "monitor": scoring_summary.get("monitor", {}),
    }

    gate = {
        "schema":           "flow_signals.gate/v2",
        "asof":             asof,
        "scored":           False,   # PRE-GATE LAW: always false pre-FS-5
        "status":           "building_history",
        "ledger": {
            "n_rows":        ledger_stats.get("n_rows", 0),
            "n_sessions":    ledger_stats.get("n_sessions", 0),
            "last_ts":       ledger_stats.get("last_ts"),
            "events_per_day_mean": epd_mean,
            "events_per_day": epd,
            "n_by_dte_bucket": n_by_dte,
        },
        "harvest": {
            "n_new_this_run": harvest_n_new,
        },
        "grader": {
            "n_graded_ok":    grade_summary.get("n_graded_ok", 0),
            "n_split_seam":   grade_summary.get("n_split_seam", 0),
            "n_not_matured":  grade_summary.get("n_not_matured", 0),
            "n_errors":       grade_summary.get("n_errors", 0),
            "elapsed_sec":    grade_summary.get("elapsed_sec", 0.0),
        },
        "scoring":          scoring_block,
        "elapsed_sec":      round(elapsed_sec, 2),
        "note": (
            "Flow-event ledger accruing. Scored field remains false until "
            "FS-3 pre-registration + FS-4 model training + FS-5 gauntlet pass. "
            f"Ledger history older than {48}h is permanently lost from the R2 "
            "archive window (FS-R1); run nightly without gaps."
        ),
    }

    tmp = gate_path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(gate, indent=2))
    tmp.rename(gate_path)
    log.info("build_flow_signals: gate.json written (v2) → %s", gate_path)


# ── run_status registration (P0.7 pattern) ───────────────────────────────────

def _register_run_status(
    n_new: int, n_graded: int, elapsed_sec: float, asof: str,
    n_scored_this_run: int = 0,
) -> None:
    """Register this run in data/run_status.json per P0.7 pattern.

    Mirrors the pattern in scripts/build_tape_flow_daily.py:_register_run_status.
    n_scored_this_run: count of events scored in this run (0 when scoring disabled).
    """
    try:
        from lib import config
        rs_path = config.data_dir() / "run_status.json"
        try:
            rs: dict = json.loads(rs_path.read_text()) if rs_path.exists() else {}
        except Exception:  # noqa: BLE001
            rs = {}
        sources = rs.setdefault("sources", {})
        sources["flow_signals"] = {
            "status":              "ok" if (n_new >= 0) else "error",
            "n_new":               n_new,
            "n_graded_ok":         n_graded,
            "n_scored_this_run":   n_scored_this_run,
            "elapsed_sec":         round(elapsed_sec, 1),
            "last_date":           asof,
            "checked_at":          datetime.now(timezone.utc).isoformat(),
        }
        tmp = rs_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rs, indent=2))
        os.replace(tmp, rs_path)
        log.info("build_flow_signals: registered run_status[flow_signals]")
    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_signals: run_status registration failed: %s", e)


# ── audit tripwire ────────────────────────────────────────────────────────────

def _audit_staleness(last_ts: str | None, today: date) -> None:
    """Warn if the ledger's last event timestamp is >= 2 trading days stale.

    Per masterplan §7 (accrual fragility) and P0.7 doctrine.
    Emits a GHA warning annotation when stale.
    """
    if not last_ts:
        log.warning("build_flow_signals: ledger has no events yet (day 1 accrual)")
        return
    try:
        from lib.nyse_calendar import is_session
        ts = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        last_date = ts.date()

        # Count trading days since last event
        d = last_date
        trading_days_since = 0
        while d < today:
            d_next = d.__class__(d.year, d.month, d.day)
            from datetime import timedelta
            d_next = d_next + timedelta(days=1)
            if is_session(d_next):
                trading_days_since += 1
            d = d_next
            if trading_days_since > 10:
                break  # cap scan

        if trading_days_since >= 2:
            log.warning(
                "::warning title=flow_signals_stale::ledger last event %s is "
                "%d trading days old — check poller / R2 outage",
                last_date, trading_days_since,
            )
        else:
            log.info("build_flow_signals: staleness ok (%d trading days since last event)",
                     trading_days_since)
    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_signals: staleness audit failed: %s", e)


# ── scoring step (FS-R7 lazy-import; never blocks pipeline) ─────────────────

def _run_scoring_step(
    flow_signals_dir: Path,
    cfg: dict,
) -> dict:
    """Score new ledger rows using per-bucket model artifacts.

    LAZY IMPORT LAW (FS-R7): lib.flow_score is imported inside this function.
    Calling this function before sklearn is available is fine — the import fails
    inside, scoring is skipped, and the function returns an empty summary.

    Returns a scoring_summary dict that feeds gate.json's "scoring" block.

    PRE-GATE LAW (amendment §9 / FS-R3):
      The scoring step is ALWAYS non-fatal. Any exception → log warning, return
      empty summary. This function must NEVER raise to the caller.

    PIT GUARD:
      Feature frame is built from ledger columns only (event-time features).
      No grade/outcome column may enter the feature frame — verified by asserting
      that grade-derived column names are absent from the features_df passed to
      score_events(). The grade column list is the canonical set from
      engine/flow_signals_grade.py (grades.parquet columns).
    """
    # Canonical grade/outcome columns that must NEVER enter the feature frame.
    # This list is the PIT guard; add new grade columns here if the grader adds them.
    _GRADE_COLS: frozenset[str] = frozenset([
        "fwd_ret", "spy_ret", "spy_excess", "outcome", "grade",
        "spy_excess_5", "spy_excess_21", "spy_excess_63", "spy_excess_126",
        "prem_touch_50", "prem_touch_100",
        "graded_at", "grade_source", "split_seam",
    ])

    try:
        scoring_cfg = cfg.get("scoring") or {}
        enabled = bool(scoring_cfg.get("enabled", False))
        if not enabled:
            log.info("build_flow_signals: scoring disabled (kill-switch off) — skipping")
            return {"enabled": False, "n_scored_this_run": 0, "n_scored_total": 0,
                    "by_status": {}, "model_versions": {}, "calibration": {}, "monitor": {}}

        # Lazy import — must succeed even if sklearn is absent (returns empty on ImportError)
        try:
            from lib import flow_score as _fs  # noqa: PLC0415
        except ImportError as e:
            log.warning("build_flow_signals: lib.flow_score unavailable (%s) — scoring skipped", e)
            return {"enabled": True, "n_scored_this_run": 0, "n_scored_total": 0,
                    "by_status": {}, "model_versions": {}, "calibration": {}, "monitor": {}}

        import pandas as _pd  # noqa: PLC0415

        # Resolve paths
        from lib import config as _cfg  # noqa: PLC0415
        ledger_path = flow_signals_dir / "ledger.parquet"
        scores_path = flow_signals_dir / "scores.parquet"
        models_dir_rel = cfg.get("models_dir", "data/flow_signals/models")
        repo_root = Path(__file__).resolve().parent.parent
        models_dir = (repo_root / models_dir_rel
                      if not Path(models_dir_rel).is_absolute()
                      else Path(models_dir_rel))

        # Load ledger
        if not ledger_path.exists():
            log.info("build_flow_signals: ledger absent — scoring skipped")
            return {"enabled": True, "n_scored_this_run": 0, "n_scored_total": 0,
                    "by_status": {}, "model_versions": {}, "calibration": {}, "monitor": {}}

        ledger = _pd.read_parquet(ledger_path)

        # Load existing scores for keep-first dedup
        existing_ids: set[str] = set()
        existing_rows: list = []
        if scores_path.exists():
            try:
                existing_df = _pd.read_parquet(scores_path)
                existing_ids = set(existing_df["event_id"].astype(str).tolist())
                existing_rows.append(existing_df)
            except Exception as e:  # noqa: BLE001
                log.warning("build_flow_signals: could not read existing scores: %s", e)

        # Filter to unscored rows
        unscored = ledger[~ledger["event_id"].astype(str).isin(existing_ids)].copy()
        if unscored.empty:
            log.info("build_flow_signals: no new events to score")
            n_total = len(existing_ids)
            _sdf = _pd.concat(existing_rows, ignore_index=True) if existing_rows else _pd.DataFrame()
            by_status = {}
            if not _sdf.empty and "status" in _sdf.columns:
                by_status = _sdf["status"].value_counts().to_dict()
            return {"enabled": True, "n_scored_this_run": 0, "n_scored_total": n_total,
                    "by_status": {str(k): int(v) for k, v in by_status.items()},
                    "model_versions": {}, "calibration": {}, "monitor": {}}

        # Score per bucket
        buckets = ["0_7", "8_90", "90p"]
        new_score_rows: list[dict] = []
        model_versions: dict[str, str | None] = {}
        calibration_info: dict[str, dict] = {}
        scored_at = datetime.now(timezone.utc).isoformat()

        for bucket in buckets:
            # Find rows for this bucket
            bucket_mask = unscored["dte_bucket"].apply(
                lambda b: _fs.map_model_bucket(str(b) if _pd.notna(b) else None) == bucket
            )
            bucket_rows = unscored[bucket_mask].copy()
            if bucket_rows.empty:
                continue

            # Check for index-root prefilter (amendment §3.3)
            # Index roots land as prefiltered_index_root (no model needed)
            is_index = bucket_rows.get("root", _pd.Series(dtype=str)).apply(
                lambda r: str(r).upper() in _INDEX_ROOTS if _pd.notna(r) else False
            ) if "root" in bucket_rows.columns else _pd.Series(False, index=bucket_rows.index)

            for eid in bucket_rows[is_index]["event_id"].astype(str).tolist():
                new_score_rows.append(_make_score_row(
                    eid,
                    underlying=bucket_rows.loc[bucket_rows["event_id"].astype(str) == eid, "root"].iloc[0]
                    if "root" in bucket_rows.columns else None,
                    dte_bucket=bucket_rows.loc[bucket_rows["event_id"].astype(str) == eid, "dte_bucket"].iloc[0]
                    if "dte_bucket" in bucket_rows.columns else None,
                    model_bucket=bucket,
                    status=_STATUS_PREFILTERED_INDEX_ROOT,
                    scored_at=scored_at,
                ))

            scoreable = bucket_rows[~is_index].copy()
            if scoreable.empty:
                continue

            # Load artifact
            artifact = _fs.load_artifact(models_dir, bucket)
            if artifact is None:
                # No model — rows get no_model status (cheap, no sklearn)
                for _, row in scoreable.iterrows():
                    new_score_rows.append(_make_score_row(
                        str(row["event_id"]),
                        underlying=row.get("root"),
                        dte_bucket=row.get("dte_bucket"),
                        model_bucket=bucket,
                        status=_STATUS_NO_MODEL,
                        scored_at=scored_at,
                    ))
                continue

            _model, _cal, manifest = artifact
            model_version = str(manifest.get("model_version", "unknown"))
            # detector_version is a frozen scores.parquet column (amendment §3.2).
            # Propagate it from the manifest so cohort lineage is traceable.
            _detector_version_from_manifest = manifest.get("detector_version")
            model_versions[bucket] = model_version
            deployable = bool(manifest.get("deployable", False))

            # Record calibration info from manifest.
            # Trainer nests ece/brier under manifest['calibration'] (not top-level).
            _cal_meta = manifest.get("calibration") or {}
            calibration_info[bucket] = {
                "ece": _cal_meta.get("ece"),
                "brier": _cal_meta.get("brier"),
                "base_rate_brier": _cal_meta.get("base_rate_brier"),
                "deployable": deployable,
                "model_version": model_version,
            }

            # Build feature frame — PIT guard: NEVER include grade/outcome columns
            feature_cols = manifest.get("cv_params", {}).get("feature_columns", [])
            if not feature_cols:
                feature_cols = [
                    c for c in scoreable.columns
                    if c not in {"event_id"} and c not in _GRADE_COLS
                    and _pd.api.types.is_numeric_dtype(scoreable[c])
                ]
            # Enforce PIT guard: reject any grade col that snuck in
            grade_cols_present = [c for c in feature_cols if c in _GRADE_COLS]
            if grade_cols_present:
                log.error(
                    "build_flow_signals: PIT GUARD: grade columns in feature frame for "
                    "bucket=%s: %s — scoring ABORTED for this bucket",
                    bucket, grade_cols_present,
                )
                for _, row in scoreable.iterrows():
                    new_score_rows.append(_make_score_row(
                        str(row["event_id"]),
                        underlying=row.get("root"),
                        dte_bucket=row.get("dte_bucket"),
                        model_bucket=bucket,
                        status=_STATUS_ERROR,
                        scored_at=scored_at,
                    ))
                continue

            # Score events
            try:
                from lib import flow_score as _fs2  # noqa: PLC0415
                score_df = _fs2.score_events(artifact, scoreable, event_id_col="event_id")
            except Exception as e:  # noqa: BLE001
                log.warning("build_flow_signals: score_events failed for bucket=%s: %s", bucket, e)
                for _, row in scoreable.iterrows():
                    new_score_rows.append(_make_score_row(
                        str(row["event_id"]),
                        underlying=row.get("root"),
                        dte_bucket=row.get("dte_bucket"),
                        model_bucket=bucket,
                        status=_STATUS_ERROR,
                        scored_at=scored_at,
                    ))
                continue

            # Build result rows
            for _, srow in score_df.iterrows():
                eid = str(srow["event_id"])
                src_rows = scoreable[scoreable["event_id"].astype(str) == eid]
                underlying = src_rows["root"].iloc[0] if "root" in scoreable.columns and len(src_rows) > 0 else None
                dte_bucket_val = src_rows["dte_bucket"].iloc[0] if "dte_bucket" in scoreable.columns and len(src_rows) > 0 else None

                score_raw = srow.get("score_raw")
                score_cal = srow.get("score_calibrated")

                if not deployable:
                    status = _STATUS_NOT_DEPLOYABLE
                    score_cal = None
                elif score_raw is None or (hasattr(score_raw, "__float__") and not math.isfinite(float(score_raw))):
                    status = _STATUS_ERROR
                else:
                    status = _STATUS_SCORED

                new_score_rows.append(_make_score_row(
                    eid,
                    underlying=underlying,
                    dte_bucket=dte_bucket_val,
                    model_bucket=bucket,
                    model_version=model_version,
                    detector_version=_detector_version_from_manifest,
                    score_raw=float(score_raw) if score_raw is not None else None,
                    score_calibrated=float(score_cal) if score_cal is not None else None,
                    status=status,
                    scored_at=scored_at,
                ))

        # Also handle rows with unmapped dte_bucket
        unmapped_mask = unscored["dte_bucket"].apply(
            lambda b: _fs.map_model_bucket(str(b) if _pd.notna(b) else None) is None
        )
        for _, row in unscored[unmapped_mask].iterrows():
            new_score_rows.append(_make_score_row(
                str(row["event_id"]),
                underlying=row.get("root"),
                dte_bucket=row.get("dte_bucket"),
                model_bucket=None,
                status=_STATUS_BUCKET_UNMAPPED,
                scored_at=scored_at,
            ))

        n_scored_this_run = len(new_score_rows)
        log.info("build_flow_signals: scored %d new events", n_scored_this_run)

        # Append to scores.parquet (atomic tmp+rename, keep-first on event_id)
        if new_score_rows:
            import pyarrow as _pa  # noqa: PLC0415 — lightweight, always available
            new_df = _pd.DataFrame(new_score_rows)
            if existing_rows:
                merged = _pd.concat([existing_rows[0], new_df], ignore_index=True)
            else:
                merged = new_df
            # keep-first dedup on event_id
            merged = merged.drop_duplicates(subset=["event_id"], keep="first")
            # Ensure column order per contract
            for col in ["event_id", "underlying", "dte_bucket", "model_bucket",
                        "model_version", "detector_version", "score_raw",
                        "score_calibrated", "status", "scored_at"]:
                if col not in merged.columns:
                    merged[col] = None
            ordered_cols = ["event_id", "underlying", "dte_bucket", "model_bucket",
                            "model_version", "detector_version", "score_raw",
                            "score_calibrated", "status", "scored_at"]
            merged = merged[ordered_cols]
            tmp = scores_path.with_suffix(".tmp.parquet")
            try:
                merged.to_parquet(tmp, index=False)
                tmp.rename(scores_path)
                log.info("build_flow_signals: scores.parquet written (%d total rows)", len(merged))
            except Exception as e:  # noqa: BLE001
                log.warning("build_flow_signals: scores.parquet write failed: %s", e)
                if tmp.exists():
                    tmp.unlink(missing_ok=True)

        # Compute by_status for gate
        all_score_rows = existing_rows[0] if existing_rows else _pd.DataFrame()
        if new_score_rows:
            new_df2 = _pd.DataFrame(new_score_rows)
            all_score_rows = _pd.concat([all_score_rows, new_df2], ignore_index=True) if not all_score_rows.empty else new_df2
        by_status: dict[str, int] = {}
        if not all_score_rows.empty and "status" in all_score_rows.columns:
            by_status = {str(k): int(v) for k, v in all_score_rows["status"].value_counts().to_dict().items()}

        # Decay monitor (amendment §8.4 / FS-R11)
        monitor = _run_decay_monitor(
            scores_path=scores_path,
            flow_signals_dir=flow_signals_dir,
            cfg=cfg,
            calibration_info=calibration_info,
        )

        return {
            "enabled": True,
            "n_scored_this_run": n_scored_this_run,
            "n_scored_total": len(existing_ids) + n_scored_this_run,
            "by_status": by_status,
            "model_versions": {k: v for k, v in model_versions.items() if v},
            "calibration": calibration_info,
            "monitor": monitor,
        }

    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_signals: scoring step failed (non-fatal): %s", e, exc_info=True)
        return {"enabled": False, "n_scored_this_run": 0, "n_scored_total": 0,
                "by_status": {}, "model_versions": {}, "calibration": {}, "monitor": {}}


def _make_score_row(
    event_id: str,
    underlying: object = None,
    dte_bucket: object = None,
    model_bucket: str | None = None,
    model_version: str | None = None,
    detector_version: str | None = None,
    score_raw: float | None = None,
    score_calibrated: float | None = None,
    status: str = _STATUS_NO_MODEL,
    scored_at: str | None = None,
) -> dict:
    """Build a scores.parquet row dict per the frozen contract."""
    if scored_at is None:
        scored_at = datetime.now(timezone.utc).isoformat()
    return {
        "event_id":          str(event_id),
        "underlying":        str(underlying) if underlying is not None else None,
        "dte_bucket":        str(dte_bucket) if dte_bucket is not None else None,
        "model_bucket":      model_bucket,
        "model_version":     model_version,
        "detector_version":  detector_version,
        "score_raw":         score_raw,
        "score_calibrated":  score_calibrated,
        "status":            status,
        "scored_at":         scored_at,
    }


def _run_decay_monitor(
    scores_path: Path,
    flow_signals_dir: Path,
    cfg: dict,
    calibration_info: dict,
) -> dict:
    """Decay monitor: per-bucket realized-vs-predicted ECE over the rolling window.

    Amendment §8.4 / FS-R11: join scores with matured grades; per bucket over the
    config window compute realized-vs-predicted ECE. On sustained breach
    (ECE >= ece_breach_threshold) set decayed=True for that bucket.

    Returns monitor dict: {bucket: {realized_ece, n, decayed}}.
    Non-fatal: on any error, returns empty dict.
    """
    try:
        import pandas as _pd  # noqa: PLC0415
        from lib import flow_score as _fs  # noqa: PLC0415

        decay_cfg = cfg.get("decay_monitor") or {}
        window_days = int(decay_cfg.get("window_days", 90))
        ece_threshold = float(decay_cfg.get("ece_breach_threshold", 0.05))

        grades_path = flow_signals_dir / "grades.parquet"
        if not scores_path.exists() or not grades_path.exists():
            return {}

        scores = _pd.read_parquet(scores_path)
        grades = _pd.read_parquet(grades_path)

        if scores.empty or grades.empty:
            return {}

        # Cutoff: only events scored/graded within the rolling window
        cutoff = _pd.Timestamp.now(tz="UTC") - _pd.Timedelta(days=window_days)

        # Join scores with grades on event_id
        joined = scores.merge(grades, on="event_id", how="inner")
        if joined.empty:
            return {}

        # Filter to window (use scored_at if available)
        if "scored_at" in joined.columns:
            joined["scored_at_dt"] = _pd.to_datetime(joined["scored_at"], utc=True, errors="coerce")
            joined = joined[joined["scored_at_dt"] >= cutoff]

        # Only scored rows with calibrated score (for ECE meaningful measurement)
        joined = joined[joined["status"] == _STATUS_SCORED]
        if joined.empty:
            return {}

        # Per-bucket label columns (mirroring config label_columns and the trainer).
        # Each bucket has its own horizon so ECE must be measured against the
        # correct outcome column — a single global label would apply the wrong
        # horizon to 2 of 3 buckets (FS4-03 fix).
        _bucket_label_cols: dict[str, list[str]] = {
            "0_7":  ["spy_excess_5", "spy_excess"],
            "8_90": ["spy_excess_21", "spy_excess"],
            "90p":  ["spy_excess_63", "spy_excess"],
        }

        monitor: dict[str, dict] = {}
        buckets = ["0_7", "8_90", "90p"]

        for bucket in buckets:
            brows = joined[joined.get("model_bucket", _pd.Series(dtype=str)) == bucket] \
                if "model_bucket" in joined.columns else _pd.DataFrame()
            if brows.empty or "score_calibrated" not in brows.columns:
                continue

            # Select the correct label column for this bucket
            label_col = None
            for col in _bucket_label_cols.get(bucket, ["spy_excess"]):
                if col in brows.columns:
                    label_col = col
                    break
            if label_col is None:
                continue

            valid = brows.dropna(subset=["score_calibrated", label_col])
            valid = valid[valid["score_calibrated"].apply(
                lambda x: isinstance(x, (int, float)) and math.isfinite(x)
            )]
            n = len(valid)
            if n < 10:
                monitor[bucket] = {"realized_ece": None, "n": n, "decayed": False}
                continue

            # Binary label: spy_excess > 0
            y = (valid[label_col].astype(float) > 0).astype(float).values
            pred = valid["score_calibrated"].astype(float).values
            realized_ece = _fs.ece(pred, y)

            # FS4-01 / FS4-02 fix: the decay monitor computes realized ECE over a
            # SINGLE rolling window.  Amendment §8.4 requires sustained breach
            # ("ECE crosses 0.05 AND STAYS THERE") before demoting a bucket.
            # Persisting consecutive-breach state across nightly runs requires a
            # state file not yet built in this wave.  Setting decayed=True on a
            # single-window crossing is therefore ADVISORY ONLY — it records the
            # observation for gate.json but does NOT suppress score_calibrated
            # (the scoring loop runs before the monitor and cannot be retroactively
            # altered here).  Suppression will be wired at FS-5 alongside persistent
            # breach-count state.  The log message is corrected to reflect this.
            decayed = False
            if realized_ece >= ece_threshold:
                decayed = True
                log.warning(
                    "::warning title=flow_score_decay::bucket=%s realized_ece=%.4f "
                    ">= threshold=%.4f over %d-day window — advisory decay flag set; "
                    "NOTE: suppression of score_calibrated for new events is NOT yet "
                    "wired (single-breach, no persistent breach-count state). "
                    "Demotion is advisory-only until FS-5 wires persistent state.",
                    bucket, realized_ece, ece_threshold, window_days,
                )

            monitor[bucket] = {
                "realized_ece": float(realized_ece) if realized_ece == realized_ece else None,
                "n": n,
                "decayed": decayed,
            }

        return monitor

    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_signals: decay monitor failed (non-fatal): %s", e)
        return {}


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flow-signal ledger nightly builder")
    parser.add_argument("--dry-run", action="store_true",
                        help="Harvest in dry-run mode; skip grader + gate write")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    t0 = time.perf_counter()
    asof = datetime.now(timezone.utc).date().isoformat()
    today = date.today()

    log.info("build_flow_signals: starting (dry_run=%s)", args.dry_run)

    # ── 1. Harvest ────────────────────────────────────────────────────────────
    try:
        from collectors.flow_signals import harvest, ledger_stats
        n_new = harvest(dry_run=args.dry_run)
        log.info("build_flow_signals: harvest complete — %d new events", n_new)
    except Exception as e:  # noqa: BLE001
        log.error("build_flow_signals: harvest failed: %s", e)
        n_new = 0

    # ── 2. Ledger stats ───────────────────────────────────────────────────────
    try:
        from collectors.flow_signals import ledger_stats as _stats
        stats = _stats()
    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_signals: ledger_stats failed: %s", e)
        stats = {"n_rows": 0, "n_sessions": 0, "dte_bucket_counts": {}, "last_ts": None}

    # ── 3. Grade matured rows ─────────────────────────────────────────────────
    grade_summary: dict = {
        "n_graded_ok": 0, "n_split_seam": 0,
        "n_not_matured": 0, "n_errors": 0, "elapsed_sec": 0.0,
    }
    if not args.dry_run:
        try:
            from engine.flow_signals_grade import grade_matured
            grade_summary = grade_matured(today=today)
            log.info("build_flow_signals: grader complete — %s", grade_summary)
        except Exception as e:  # noqa: BLE001
            log.error("build_flow_signals: grader failed: %s", e)

    # ── 3b. Score new events (FS-R7 lazy-import; non-fatal) ──────────────────
    scoring_summary: dict = {}
    if not args.dry_run:
        try:
            import yaml as _yaml  # noqa: PLC0415
            _cfg_path = Path(__file__).resolve().parent.parent / "config" / "flow_score.yml"
            if not _cfg_path.exists():
                log.info("build_flow_signals: config/flow_score.yml absent — scoring disabled")
                scoring_summary = {"enabled": False, "n_scored_this_run": 0, "n_scored_total": 0,
                                   "by_status": {}, "model_versions": {}, "calibration": {},
                                   "monitor": {}}
            else:
                _fs_cfg = _yaml.safe_load(_cfg_path.read_text()) or {}
                from lib import config as _cfg_lib  # noqa: PLC0415
                _fs_dir = _cfg_lib.data_dir() / "flow_signals"
                scoring_summary = _run_scoring_step(_fs_dir, _fs_cfg)
                log.info(
                    "build_flow_signals: scoring step complete — n_scored_this_run=%d",
                    scoring_summary.get("n_scored_this_run", 0),
                )
        except Exception as e:  # noqa: BLE001
            log.warning("build_flow_signals: scoring step error (non-fatal): %s", e)
            scoring_summary = {"enabled": False, "n_scored_this_run": 0, "n_scored_total": 0,
                               "by_status": {}, "model_versions": {}, "calibration": {},
                               "monitor": {}}

    elapsed_sec = time.perf_counter() - t0

    # ── 4. Write gate.json (v2) ───────────────────────────────────────────────
    if not args.dry_run:
        try:
            from lib import config
            gate_path = config.data_dir() / "flow_signals" / "gate.json"
            gate_path.parent.mkdir(parents=True, exist_ok=True)
            _write_gate(gate_path, stats, grade_summary, n_new, elapsed_sec, asof,
                        scoring_summary=scoring_summary)
        except Exception as e:  # noqa: BLE001
            log.error("build_flow_signals: gate.json write failed: %s", e)

    # ── 5. run_status registration ────────────────────────────────────────────
    if not args.dry_run:
        _register_run_status(
            n_new, grade_summary.get("n_graded_ok", 0), elapsed_sec, asof,
            n_scored_this_run=int(scoring_summary.get("n_scored_this_run", 0)),
        )

    # ── 6. Audit staleness tripwire ───────────────────────────────────────────
    _audit_staleness(stats.get("last_ts"), today)

    # ── Timing ───────────────────────────────────────────────────────────────
    log.info(
        "[timing] build_flow_signals: total=%.2fs harvest=%d_events "
        "ledger_rows=%d graded_ok=%d",
        elapsed_sec, n_new, stats.get("n_rows", 0),
        grade_summary.get("n_graded_ok", 0),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
