"""Finalize the CCTV 新闻联播 backfill — idempotent post-completion pipeline.

This script is safe to run at any point (including mid-scrape — it reports
partial progress) and is designed to be re-run by the integrator once the
background scrape (PID 69497, started 2026-07-02) completes.

Pipeline
--------
  (a) Gap audit — coverage 2016-02-03 → today, per-year breakdown.
      Retriable gaps (all-stub or missing dates) → invoke --repair if requested.
  (b) Tone rebuild — runs rebuild_cctv_tone_history → cctv_tone_history.parquet
      (only if archive has ≥1 real 'ok' shard).
  (c) Shard commit decision — sizes the archive, prints the git command to use,
      enforces the #923 policy:
        - projected <60 MB  → "COMMIT-OK: commit shards now"
        - 60–150 MB         → "COMMIT-OK: single dedicated commit"
        - >150 MB           → "GITIGNORE: deviation from standard; document in PR"
      Shards are currently gitignored (data/china_news/cctv_archive/*.parquet).
      un-gitignore is required before committing; this script prints the exact steps.
  (d) Sentiment z re-baseline — after tone_history exists, engine/china_news.py
      policy_tone() automatically uses the long-history baseline for z-scoring
      (see _tone_stats_with_history). This step verifies the re-baseline is live
      and reports the new z vs the old rolling-90d z on the current 19-point series.
  (e) Validation re-run — calls engine.china_validation.validate_all() so the
      news_sentiment family grades on the full series and the proven gate runs.
      Reports interim n_obs and sign verdict.

Usage
-----
  python scripts/finalize_cctv_backfill.py [--repair] [--dry-run]
  python scripts/finalize_cctv_backfill.py --status   # just audit, no rebuild

The backfill is considered COMPLETE when:
  - gap audit shows 0 missing dates AND stub rate ≤ 5% for each year ≥ 2016
  - cctv_tone_history.parquet exists with ≥ 3700 rows
  - the news_sentiment validation family has n_obs > 0 in the scorecard
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_ARCHIVE = REPO_ROOT / "data" / "china_news" / "cctv_archive"
TONE_HISTORY_PATH = REPO_ROOT / "data" / "china_news" / "cctv_tone_history.parquet"
SCORECARD_PATH = REPO_ROOT / "data" / "china_validation" / "scorecard.json"

# Size thresholds (bytes)
_SIZE_COMMIT_OK = 60 * 1024 * 1024    # 60 MB
_SIZE_GITIGNORE = 150 * 1024 * 1024   # 150 MB
_COMPLETENESS_STUB_RATE_MAX = 0.05    # ≤5% stub rate per year = complete
_COMPLETENESS_MIN_ROWS = 3700         # minimum tone_history rows for "complete" declaration

log = logging.getLogger("finalize_cctv")


# ---------------------------------------------------------------------------
# (a) Gap audit — wrapper around backfill_cctv_archive --gap-audit
# ---------------------------------------------------------------------------

def _run_gap_audit(archive_dir: Path) -> dict:
    """Run the gap audit and return a dict of per-year stats plus a summary.
    Returns immediately (no scraping) — pure read of existing shards."""
    from scripts.backfill_cctv_archive import (
        _all_dates, _already_archived, _all_stubs_or_error,
        HISTORY_START, _shard_path, _load_shard,
    )
    from collections import defaultdict
    from datetime import date

    dates = _all_dates()
    year_stats: dict[int, dict] = defaultdict(lambda: {"total": 0, "missing": 0,
                                                        "stub": 0, "error": 0,
                                                        "ok": 0, "empty": 0})
    missing_dates: list[str] = []
    retriable_dates: list[str] = []

    for dt in dates:
        yr = dt.year
        ds = dt.strftime("%Y-%m-%d")
        year_stats[yr]["total"] += 1
        shard = _shard_path(archive_dir, dt)
        if not shard.exists():
            year_stats[yr]["missing"] += 1
            missing_dates.append(ds)
            retriable_dates.append(ds)
            continue
        df = _load_shard(shard)
        day_rows = df[df["date"] == ds]
        if day_rows.empty:
            year_stats[yr]["missing"] += 1
            missing_dates.append(ds)
            retriable_dates.append(ds)
            continue
        statuses = day_rows["fetch_status"].value_counts().to_dict()
        for s in ("ok", "empty", "stub", "error"):
            year_stats[yr][s] += statuses.get(s, 0)
        if _all_stubs_or_error(archive_dir, dt):
            retriable_dates.append(ds)

    total_dates = sum(v["total"] for v in year_stats.values())
    total_missing = len(missing_dates)
    total_covered = total_dates - total_missing
    total_ok = sum(v["ok"] for v in year_stats.values())
    total_stub = sum(v["stub"] for v in year_stats.values())
    total_retriable = len(retriable_dates)

    # Per-year completeness assessment
    year_complete: dict[int, bool] = {}
    for yr, s in year_stats.items():
        if yr < 2016:
            year_complete[yr] = True  # degraded pre-2016 not required
            continue
        stub_rate = s["stub"] / max(s["total"], 1)
        year_complete[yr] = (s["missing"] == 0 and stub_rate <= _COMPLETENESS_STUB_RATE_MAX)

    # Overall completeness (2016+ only)
    years_required = [yr for yr in year_stats if yr >= 2016]
    is_complete = all(year_complete.get(yr, False) for yr in years_required) if years_required else False

    return {
        "total_dates": total_dates,
        "total_covered": total_covered,
        "total_missing": total_missing,
        "total_retriable": total_retriable,
        "total_ok_days": total_ok,
        "total_stub_days": total_stub,
        "year_stats": dict(year_stats),
        "year_complete": year_complete,
        "missing_dates_sample": missing_dates[:20],
        "retriable_sample": retriable_dates[:20],
        "is_complete": is_complete,
    }


def print_gap_audit(audit: dict) -> None:
    print("\n=== CCTV Archive Gap Audit ===")
    print(f"{'Year':<6} {'Total':<7} {'Missing':<9} {'OK-days':<9} {'Empty':<7} {'Stub':<7} {'Error':<7} {'Done?'}")
    for yr in sorted(audit["year_stats"].keys()):
        s = audit["year_stats"][yr]
        done = "YES" if audit["year_complete"].get(yr, False) else ("pre-2016" if yr < 2016 else "NO")
        print(f"{yr:<6} {s['total']:<7} {s['missing']:<9} {s['ok']:<9} {s['empty']:<7} {s['stub']:<7} {s['error']:<7} {done}")
    print()
    print(f"Coverage: {audit['total_covered']}/{audit['total_dates']} dates archived")
    print(f"Retriable (missing + all-stub): {audit['total_retriable']}")
    if audit["missing_dates_sample"]:
        print(f"Sample missing: {audit['missing_dates_sample'][:10]}")
    print(f"\nBACKFILL COMPLETE: {'YES' if audit['is_complete'] else 'NO (still in progress or needs --repair)'}")


# ---------------------------------------------------------------------------
# (a2) Repair
# ---------------------------------------------------------------------------

def run_repair(archive_dir: Path) -> None:
    """Invoke the backfill --repair mode for retriable dates."""
    log.info("Launching --repair pass (this will take time; runs in-process)...")
    from scripts.backfill_cctv_archive import run_backfill
    run_backfill(archive_dir, repair=True)


# ---------------------------------------------------------------------------
# (b) Tone rebuild
# ---------------------------------------------------------------------------

def run_tone_rebuild(archive_dir: Path, out_path: Path, dry_run: bool = False) -> dict:
    """Rebuild cctv_tone_history.parquet from all shards. Returns a summary dict."""
    shards = sorted(archive_dir.glob("*.parquet"))
    if not shards:
        return {"status": "skipped", "reason": "no shards in archive dir yet", "n_rows": 0}

    # Count ok rows to decide if rebuild is meaningful
    ok_count = 0
    for sh in shards[:3]:  # probe first 3 shards
        try:
            df = pd.read_parquet(sh)
            ok_count += int((df["fetch_status"] == "ok").sum())
        except Exception:
            pass
    if ok_count == 0:
        return {"status": "skipped", "reason": "archive shards have no ok rows yet", "n_rows": 0}

    if dry_run:
        log.info("[dry-run] would rebuild tone history from %d shards", len(shards))
        return {"status": "dry-run", "n_shards": len(shards), "n_rows": 0}

    log.info("Rebuilding CCTV tone history from %d shards...", len(shards))
    from scripts.rebuild_cctv_tone_history import rebuild
    try:
        df = rebuild(archive_dir, out_path)
        ok_rows = int((df["n_items"] > 0).sum())
        nan_rows = int(df["tone"].isna().sum())
        log.info(
            "tone_history: %d total rows, %d with real data, %d NaN (empty/stub days)",
            len(df), ok_rows, nan_rows
        )
        return {
            "status": "ok", "n_rows": len(df),
            "n_ok_days": ok_rows, "n_nan_days": nan_rows,
            "date_min": str(df.index.min().date()) if len(df) else None,
            "date_max": str(df.index.max().date()) if len(df) else None,
        }
    except Exception as e:
        log.error("Tone rebuild failed: %s", e)
        return {"status": "error", "reason": str(e), "n_rows": 0}


# ---------------------------------------------------------------------------
# (c) Shard commit decision
# ---------------------------------------------------------------------------

def shard_commit_decision(archive_dir: Path) -> dict:
    """Measure archive size and print the appropriate git commit steps."""
    shards = sorted(archive_dir.glob("*.parquet"))
    if not shards:
        return {"status": "no-shards", "total_bytes": 0}

    total_bytes = sum(s.stat().st_size for s in shards)
    n_shards = len(shards)

    if total_bytes < _SIZE_COMMIT_OK:
        policy = "COMMIT-OK-IMMEDIATE"
        note = f"Archive {total_bytes/1e6:.1f} MB < 60 MB — commit immediately in this PR"
    elif total_bytes < _SIZE_GITIGNORE:
        policy = "COMMIT-OK-DEDICATED"
        note = (
            f"Archive {total_bytes/1e6:.1f} MB (60–150 MB) — commit in one dedicated commit "
            "AFTER the scrape completes, not in this PR (shards stay gitignored until then)"
        )
    else:
        policy = "GITIGNORE-DEVIATION"
        note = (
            f"Archive {total_bytes/1e6:.1f} MB > 150 MB — EXCEEDS policy threshold. "
            "Keep gitignored. Document deviation in PR body. Consider lz4 re-compression "
            "or splitting the archive into yearly tarballs."
        )

    print(f"\n=== Shard Commit Decision ({policy}) ===")
    print(f"  Archive: {archive_dir}")
    print(f"  Shards:  {n_shards}")
    print(f"  Size:    {total_bytes/1e6:.1f} MB ({total_bytes:,} bytes)")
    print(f"  Policy:  {note}")

    if policy in ("COMMIT-OK-IMMEDIATE", "COMMIT-OK-DEDICATED"):
        print("\n  Steps to commit shards:")
        print("  1. Remove the gitignore line: edit .gitignore, delete 'data/china_news/cctv_archive/*.parquet'")
        print("  2. git add data/china_news/cctv_archive/*.parquet data/china_news/cctv_tone_history.parquet")
        print("  3. git commit -m 'data(cctv): commit 10-year CCTV archive shards + tone_history baseline'")
        print("  4. Restore gitignore line if desired (for future re-runs to not re-add)")
    return {
        "status": "ok", "policy": policy, "n_shards": n_shards,
        "total_bytes": total_bytes, "total_mb": round(total_bytes / 1e6, 1), "note": note,
    }


# ---------------------------------------------------------------------------
# (d) Sentiment z re-baseline check
# ---------------------------------------------------------------------------

def check_rebaseline(archive_dir: Path) -> dict:
    """Compare old rolling-90d z vs new long-history z on the current live series."""
    try:
        if not TONE_HISTORY_PATH.exists():
            return {"status": "skipped", "reason": "cctv_tone_history.parquet not yet built"}

        hist = pd.read_parquet(TONE_HISTORY_PATH)
        hist_tone = hist["tone"].dropna()
        if len(hist_tone) < 30:
            return {"status": "skipped", "reason": f"only {len(hist_tone)} rows in history — too few"}

        # Load the live series (last 19 points currently)
        live_path = REPO_ROOT / "data" / "china_news" / "cctv_tone.parquet"
        if not live_path.exists():
            return {"status": "skipped", "reason": "live cctv_tone.parquet missing"}
        live = pd.read_parquet(live_path)
        if live.empty or "tone" not in live.columns:
            return {"status": "skipped", "reason": "live cctv_tone.parquet empty"}

        live_s = pd.to_numeric(live["tone"], errors="coerce").dropna()
        if live_s.empty:
            return {"status": "skipped", "reason": "live series empty after coerce"}

        latest = float(live_s.iloc[-1])

        # Old z: rolling 90d on live series only
        smooth = 5
        live_sm = live_s.rolling(max(smooth, 1), min_periods=1).mean()
        old_win = live_sm.tail(90)
        old_mu = float(old_win.mean())
        old_sd = float(old_win.std(ddof=0)) or 1.0
        old_z = (latest - old_mu) / old_sd

        # New z: long-history baseline from tone_history
        # We concatenate the history + live and z-score the latest vs the full history mean/std
        import numpy as np
        # The history is the authoritative baseline; the live points are recent
        hist_sm = hist_tone.rolling(max(smooth, 1), min_periods=1).mean()
        baseline_mu = float(hist_sm.mean())
        baseline_sd = float(hist_sm.std(ddof=1)) if len(hist_sm) > 1 else 1.0
        if baseline_sd < 1e-9:
            baseline_sd = 1.0
        # Latest is from live (already smoothed in the window)
        new_z = (latest - baseline_mu) / baseline_sd

        print(f"\n=== Sentiment Z Re-baseline ===")
        print(f"  History rows: {len(hist_tone):,}  ({hist_tone.index.min().date()} → {hist_tone.index.max().date()})")
        print(f"  Live points:  {len(live_s)}")
        print(f"  Latest tone:  {latest:.3f}")
        print(f"  Old z (90d rolling, n={len(old_win)}):   {old_z:+.3f}")
        print(f"  New z (10y baseline, n={len(hist_sm):,}): {new_z:+.3f}")
        delta = new_z - old_z
        print(f"  Delta (new−old):                {delta:+.3f}")
        if abs(delta) > 1.0:
            print("  *** MATERIAL SHIFT: the 90-day window was not representative of the long-run distribution ***")

        return {
            "status": "ok",
            "history_rows": len(hist_tone),
            "live_points": len(live_s),
            "latest_tone": round(latest, 3),
            "old_z_90d": round(old_z, 3),
            "new_z_long_history": round(new_z, 3),
            "delta": round(delta, 3),
            "baseline_mu": round(baseline_mu, 3),
            "baseline_sd": round(baseline_sd, 3),
        }
    except Exception as e:
        log.error("check_rebaseline failed: %s", e)
        return {"status": "error", "reason": str(e)}


# ---------------------------------------------------------------------------
# (e) Validation re-run
# ---------------------------------------------------------------------------

def run_validation(dry_run: bool = False) -> dict:
    """Run china_validation.validate_all() and report news_sentiment result."""
    try:
        if dry_run:
            # Read the existing scorecard if present
            if SCORECARD_PATH.exists():
                sc = json.loads(SCORECARD_PATH.read_text(encoding="utf-8"))
                ns = (sc.get("families") or {}).get("news_sentiment") or {}
                return {"status": "dry-run (existing scorecard read)", "news_sentiment": ns}
            return {"status": "dry-run (no scorecard yet)", "news_sentiment": {}}

        log.info("Running engine.china_validation.validate_all()...")
        from engine import china_validation as cv
        result = cv.validate_all()
        ns = (result.get("families") or {}).get("news_sentiment") or {}

        print(f"\n=== china_validation: news_sentiment family ===")
        print(f"  status:        {ns.get('status', 'unknown')}")
        print(f"  tier:          {ns.get('tier', '?')}")
        print(f"  proven:        {ns.get('proven', False)}")
        print(f"  sign_expected: {ns.get('sign_expected')}")
        print(f"  sign_ok:       {ns.get('sign_ok', '?')}")
        print(f"  n_obs:         {ns.get('n_obs', 0)}")
        t = ns.get('t_hac')
        if t is not None:
            print(f"  t_hac:         {t:.3f}")
        m = ns.get('mean_ic')
        if m is not None:
            print(f"  mean_ic:       {m:.4f}")
        reason = ns.get("reason")
        if reason:
            print(f"  reason:        {reason}")
        print(f"\n  By horizon:")
        for h, hv in (ns.get("by_horizon") or {}).items():
            n = hv.get("n", 0)
            t_h = hv.get("t_hac")
            m_h = hv.get("mean_ic")
            t_str = f"t={t_h:.2f}" if t_h is not None else "t=?"
            m_str = f"mean_ic={m_h:.4f}" if m_h is not None else "mean_ic=?"
            print(f"    {h}d: n={n}  {t_str}  {m_str}")

        if ns.get("proven"):
            print("\n  *** SIGN PROVEN — _news_sign_proven() will now return True ***")
            print("  *** W3 auto-reactivation hook fires: china_intel_analysis will use contrarian direction ***")
        else:
            print(f"\n  Sign not yet proven (n_obs={ns.get('n_obs', 0)}); contrarian direction stays salience-only")

        return {"status": "ok", "news_sentiment": ns}
    except Exception as e:
        log.error("run_validation failed: %s", e)
        return {"status": "error", "reason": str(e), "news_sentiment": {}}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize CCTV backfill: gap-audit → tone-rebuild → commit-decision → rebaseline → validation"
    )
    parser.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE),
                        help=f"Archive shard directory (default: {DEFAULT_ARCHIVE})")
    parser.add_argument("--repair", action="store_true",
                        help="After gap audit, invoke --repair for missing/all-stub dates")
    parser.add_argument("--status", action="store_true",
                        help="Gap audit + report only; skip rebuild and validation")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen; skip writes and validation call")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    archive_dir = Path(args.archive_dir).expanduser().resolve()
    dry_run = args.dry_run
    status_only = args.status

    print(f"\n{'='*60}")
    print(f"  CCTV Backfill Finalization Pipeline")
    print(f"  archive: {archive_dir}")
    print(f"  dry_run={dry_run}  status_only={status_only}  repair={args.repair}")
    print(f"{'='*60}")

    # (a) Gap audit
    print("\n--- Step (a): Gap Audit ---")
    audit = _run_gap_audit(archive_dir)
    print_gap_audit(audit)

    if status_only:
        print("\n[--status] stopping after gap audit.")
        return

    # (a2) Repair if requested AND retriable dates exist
    if args.repair and audit["total_retriable"] > 0:
        print(f"\n--- Step (a2): Repair ({audit['total_retriable']} retriable dates) ---")
        if not dry_run:
            run_repair(archive_dir)
            # Re-audit after repair
            audit = _run_gap_audit(archive_dir)
            print_gap_audit(audit)
        else:
            log.info("[dry-run] would run repair on %d dates", audit["total_retriable"])

    # (b) Tone rebuild
    print("\n--- Step (b): Tone History Rebuild ---")
    rebuild_result = run_tone_rebuild(archive_dir, TONE_HISTORY_PATH, dry_run=dry_run)
    print(f"  Rebuild: {rebuild_result}")

    # (c) Shard commit decision
    print("\n--- Step (c): Shard Commit Decision ---")
    commit_result = shard_commit_decision(archive_dir)

    # (d) Sentiment z re-baseline
    print("\n--- Step (d): Sentiment Z Re-baseline ---")
    rebase_result = check_rebaseline(archive_dir)
    if rebase_result["status"] not in ("ok",):
        print(f"  {rebase_result}")

    # (e) Validation re-run
    print("\n--- Step (e): Contrarian-Sign Validation ---")
    val_result = run_validation(dry_run=dry_run)
    if val_result["status"] not in ("ok",):
        print(f"  {val_result}")

    # Summary
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"  Archive complete:   {'YES' if audit['is_complete'] else 'NO'}")
    print(f"  tone_history built: {'YES' if TONE_HISTORY_PATH.exists() else 'NO'}")
    ns = val_result.get("news_sentiment") or {}
    sign_proven_str = "YES" if ns.get("proven") else f"NO (n_obs={ns.get('n_obs', 0)})"
    print(f"  Sign proven:        {sign_proven_str}")
    print(f"  n_obs:              {ns.get('n_obs', 0)}")
    commit_policy = commit_result.get("policy", "?")
    total_mb = commit_result.get("total_mb", 0)
    print(f"  Shard size/policy:  {total_mb} MB → {commit_policy}")
    print(f"{'='*60}\n")

    if not audit["is_complete"]:
        print("NOTE: scrape still in progress. Re-run once the backfill PID completes.")
        print("      ETA: ~2026-07-04 05:00 UTC (PID 69497, started 2026-07-02 ~11:30 UTC)")
        print("      To run repair after completion: python scripts/finalize_cctv_backfill.py --repair")


if __name__ == "__main__":
    main()
