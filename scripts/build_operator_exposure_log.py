"""scripts/build_operator_exposure_log.py — W-EX operator exposure log builder.

NEXT3 program §5.2 (W-EX), RUL-U6.

Records what the operator was *shown* (exposure) from committed site artifacts so
the denominator tape for decision-quality analysis exists.  No statistics, no
contrasts, no trial registrations (RUL-U6 fence).

JOIN CONTRACT
-------------
Action rows from data/operator/action_ledger.jsonl join on surface conventions
(surface string values are identical here and there).  Unmatched actions are
counted and reported, never dropped — mirroring engine/operator_grading.py's
unmatched-accounting convention (n_unmatched_actions counted, not silently
discarded).  This script does NOT read the action ledger itself (RUL-U6 fence);
the join is documented here so downstream consumers of both files can implement
it without re-deriving the convention.

EXPOSURE DATE
-------------
Exposure date = each artifact's as_of field, never the script run date.
Rationale: site artifacts are committed by the nightly pipeline; the collect
job runs in a separate nightly step that reads already-committed artifacts.
Using the artifact's as_of avoids date-skew from multi-hour pipelines.

SURFACES v1
-----------
- experiment    site/marketdata/experiments.json        id verbatim
- board_buy     site/factordata/us_standouts.json       buy-lane tickers
- board_watch   site/factordata/us_standouts.json       watch-lane tickers
- alert_wh      site/wh_banner.json                     alert id verbatim
- alert_rr      site/rr_banner.json                     only when alert != null

OUTPUTS
-------
- data/operator/exposure_log.jsonl         gitignored host-local; append-only;
                                           dedup on (surface, surface_id, as_of)
- data/governance/operator_exposure_summary.json  committed; counts by surface×day;
                                           bounded 90 days; vintage-stamped

SCHEMA
------
Each row:
  {"schema":"operator_exposure.v1","ts_logged":"ISO","as_of":"YYYY-MM-DD",
   "surface":"experiment|board_buy|board_watch|alert_wh|alert_rr",
   "surface_id":"string","artifact":"path","exposure_kind":"standing|new|come_back_due"}

KNOWN SURFACES for surface_id (downstream join key):
  experiment:    id field verbatim from experiments.json
  board_buy:     sha1(as_of + "|" + lane + "|" + ticker)[:12]
  board_watch:   sha1(as_of + "|" + lane + "|" + ticker)[:12]
  alert_wh:      id field verbatim from wh_banner.json alerts[]
  alert_rr:      id field verbatim from rr_banner.json alert (when alert != null)

Usage::

    python -m scripts.build_operator_exposure_log
    python -m scripts.build_operator_exposure_log --root /path/to/repo
    python -m scripts.build_operator_exposure_log --dry-run   # prints, no writes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("build_operator_exposure_log")

SCHEMA_ROW = "operator_exposure.v1"
SCHEMA_SUMMARY = "operator_exposure_summary.v1"

# Known lane→surface mappings for us_standouts.json.
# Unexpected lanes are counted + logged, never dropped silently (RUL-U6).
_KNOWN_LANE_SURFACES: dict[str, str] = {
    "continuation": "board_buy",
    "bottoming": "board_buy",
    "watch": "board_watch",
}

# Summary is bounded to the most recent 90 days.
_SUMMARY_MAX_DAYS = 90


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha1_id(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def _date_from_iso(s: str | None) -> str | None:
    """Return YYYY-MM-DD from an ISO datetime or date string, or None."""
    if not s:
        return None
    return s[:10]  # works for both "2026-07-06" and "2026-07-06T13:00:00+00:00"


def _load_json(path: Path) -> dict | None:
    """Load a JSON file; return None if absent or parse failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("could not read %s: %s", path, exc)
        return None


def _load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file; return empty list if absent or parse failure."""
    if not path.exists():
        return []
    try:
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    except Exception as exc:
        log.warning("could not read %s: %s", path, exc)
        return []


# ---------------------------------------------------------------------------
# Exposure generators — one per surface
# ---------------------------------------------------------------------------

def _rows_experiments(data: dict, artifact: str) -> list[dict]:
    """Generate exposure rows from experiments.json."""
    as_of: str | None = data.get("as_of")
    if not as_of:
        log.warning("[experiments] missing as_of field in %s — skipping surface", artifact)
        return []

    experiments = data.get("experiments", [])
    if not isinstance(experiments, list):
        log.warning("[experiments] unexpected type for 'experiments' key in %s", artifact)
        return []

    ts = _now_iso()
    rows: list[dict] = []
    for exp in experiments:
        exp_id = exp.get("id")
        if not exp_id:
            continue

        come_back_on = exp.get("come_back_on")
        if come_back_on and come_back_on <= as_of:
            exposure_kind = "come_back_due"
        else:
            exposure_kind = "standing"
        # "new" kind is determined at dedup time (first appearance of an id).
        # We tag it here as "standing" conservatively; the dedup + append logic
        # upgrades it to "new" when the (surface, surface_id, as_of) triplet has
        # not appeared before in the existing log.

        rows.append({
            "schema": SCHEMA_ROW,
            "ts_logged": ts,
            "as_of": as_of,
            "surface": "experiment",
            "surface_id": exp_id,
            "artifact": artifact,
            "exposure_kind": exposure_kind,
        })
    return rows


def _rows_standouts(data: dict, artifact: str) -> tuple[list[dict], int]:
    """Generate exposure rows from us_standouts.json.

    Returns (rows, n_unknown_lanes).
    Unknown lanes are counted and logged; no rows are dropped silently.
    """
    as_of: str | None = data.get("as_of")
    if not as_of:
        log.warning("[standouts] missing as_of field in %s — skipping surface", artifact)
        return [], 0

    ts = _now_iso()
    rows: list[dict] = []
    n_unknown_lanes = 0

    for pool_key in ("buy", "watch"):
        pool = data.get(pool_key, [])
        if not isinstance(pool, list):
            continue
        for item in pool:
            ticker = item.get("ticker")
            lane = item.get("lane")
            if not ticker:
                continue

            surface = _KNOWN_LANE_SURFACES.get(lane) if lane else None
            if surface is None:
                n_unknown_lanes += 1
                log.warning(
                    "[standouts] unknown lane %r for ticker %s (as_of=%s) — "
                    "counting but not dropping",
                    lane, ticker, as_of,
                )
                # Assign a fallback surface name derived from pool_key so the
                # row is still recorded with an informative surface string.
                surface = f"board_{pool_key}"

            surface_id = _sha1_id(f"{as_of}|{lane or ''}|{ticker}")
            rows.append({
                "schema": SCHEMA_ROW,
                "ts_logged": ts,
                "as_of": as_of,
                "surface": surface,
                "surface_id": surface_id,
                "artifact": artifact,
                "exposure_kind": "standing",
            })

    return rows, n_unknown_lanes


def _rows_wh_banner(data: dict, artifact: str) -> list[dict]:
    """Generate exposure rows from wh_banner.json.

    as_of is derived from each alert's published_at date (the file carries no
    top-level as_of field).
    """
    alerts = data.get("alerts", [])
    if not isinstance(alerts, list):
        return []

    ts = _now_iso()
    rows: list[dict] = []
    for alert in alerts:
        alert_id = alert.get("id")
        published_at = alert.get("published_at")
        as_of = _date_from_iso(published_at)
        if not alert_id or not as_of:
            log.warning("[wh_banner] alert missing id or published_at — skipping row")
            continue
        rows.append({
            "schema": SCHEMA_ROW,
            "ts_logged": ts,
            "as_of": as_of,
            "surface": "alert_wh",
            "surface_id": alert_id,
            "artifact": artifact,
            "exposure_kind": "standing",
        })
    return rows


def _rows_rr_banner(data: dict, artifact: str) -> list[dict]:
    """Generate exposure rows from rr_banner.json.

    The file is ALWAYS present and git-tracked.  It carries {"alert": null}
    when no risk-off extreme is active.  The exposure signal is alert != null,
    never file absence.  The date field is spelled "asof" (no underscore).
    When alert is null: emit zero rows (no active exposure).
    """
    alert = data.get("alert")
    if alert is None:
        # No active risk-off extreme — zero exposure rows for this surface.
        log.debug("[rr_banner] alert is null — 0 rows emitted (by design)")
        return []

    # "asof" spelled without underscore per §2.5.5 / §5.2
    as_of = data.get("asof")
    if not as_of:
        log.warning("[rr_banner] alert != null but missing 'asof' field — skipping")
        return []

    alert_id = alert.get("id") if isinstance(alert, dict) else str(alert)
    if not alert_id:
        log.warning("[rr_banner] alert has no id field — skipping")
        return []

    return [{
        "schema": SCHEMA_ROW,
        "ts_logged": _now_iso(),
        "as_of": as_of,
        "surface": "alert_rr",
        "surface_id": alert_id,
        "artifact": artifact,
        "exposure_kind": "standing",
    }]


# ---------------------------------------------------------------------------
# Dedup logic
# ---------------------------------------------------------------------------

def _dedup_key(row: dict) -> tuple[str, str, str]:
    return (row["surface"], row["surface_id"], row["as_of"])


def _mark_new_rows(new_rows: list[dict], existing_keys: set[tuple]) -> list[dict]:
    """For rows whose dedup key is not in existing_keys, upgrade exposure_kind to 'new'."""
    out = []
    for row in new_rows:
        k = _dedup_key(row)
        if k not in existing_keys:
            r = dict(row)
            # Upgrade to "new" only if it was "standing" (don't downgrade "come_back_due")
            if r["exposure_kind"] == "standing":
                r["exposure_kind"] = "new"
            out.append(r)
        # Rows already present are silently deduplicated (not re-appended)
    return out


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def _build_summary(all_rows: list[dict], generated_at: str, as_of_today: str) -> dict:
    """Build the 90-day bounded summary counts-by-surface-x-day."""
    from collections import defaultdict
    from datetime import timedelta

    # Cutoff: only last 90 days
    ref_date = date.fromisoformat(as_of_today) if as_of_today else date.today()
    cutoff = (ref_date - timedelta(days=_SUMMARY_MAX_DAYS)).isoformat()

    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_rows = 0
    for row in all_rows:
        row_as_of = row.get("as_of", "")
        if row_as_of < cutoff:
            continue
        surface = row.get("surface", "unknown")
        counts[row_as_of][surface] += 1
        total_rows += 1

    # Flatten to sorted list
    by_day = []
    for day_str in sorted(counts.keys()):
        by_day.append({
            "as_of": day_str,
            "counts": dict(counts[day_str]),
        })

    return {
        "schema": SCHEMA_SUMMARY,
        "generated_at": generated_at,
        "window_days": _SUMMARY_MAX_DAYS,
        "n_rows_in_window": total_rows,
        "by_day": by_day,
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(root: Path | None = None, dry_run: bool = False) -> dict:
    """Build the operator exposure log.  Returns a status dict."""
    if root is None:
        root = Path(__file__).resolve().parent.parent

    generated_at = _now_iso()
    n_unknown_lanes_total = 0

    # ── load site artifacts ────────────────────────────────────────────────
    exp_path = root / "site" / "marketdata" / "experiments.json"
    standouts_path = root / "site" / "factordata" / "us_standouts.json"
    wh_path = root / "site" / "wh_banner.json"
    rr_path = root / "site" / "rr_banner.json"

    exp_data = _load_json(exp_path)
    standouts_data = _load_json(standouts_path)
    wh_data = _load_json(wh_path)
    rr_data = _load_json(rr_path)

    # ── generate new rows ──────────────────────────────────────────────────
    new_rows: list[dict] = []

    if exp_data is not None:
        new_rows.extend(_rows_experiments(exp_data, "site/marketdata/experiments.json"))
    else:
        log.warning("[experiments] artifact missing — 0 rows")

    if standouts_data is not None:
        s_rows, n_unknown = _rows_standouts(standouts_data, "site/factordata/us_standouts.json")
        new_rows.extend(s_rows)
        n_unknown_lanes_total += n_unknown
    else:
        log.warning("[standouts] artifact missing — 0 rows")

    if wh_data is not None:
        new_rows.extend(_rows_wh_banner(wh_data, "site/wh_banner.json"))
    else:
        log.warning("[wh_banner] artifact missing — 0 rows")

    if rr_data is not None:
        new_rows.extend(_rows_rr_banner(rr_data, "site/rr_banner.json"))
    else:
        log.warning("[rr_banner] artifact missing — 0 rows")

    log.info(
        "exposure rows generated: %d (experiments=%d standouts=%d wh=%d rr=%d "
        "unknown_lanes=%d)",
        len(new_rows),
        sum(1 for r in new_rows if r["surface"] == "experiment"),
        sum(1 for r in new_rows if r["surface"].startswith("board_")),
        sum(1 for r in new_rows if r["surface"] == "alert_wh"),
        sum(1 for r in new_rows if r["surface"] == "alert_rr"),
        n_unknown_lanes_total,
    )

    # ── dedup against existing log ─────────────────────────────────────────
    log_path = root / "data" / "operator" / "exposure_log.jsonl"
    existing_rows = _load_jsonl(log_path)
    existing_keys: set[tuple] = {_dedup_key(r) for r in existing_rows}

    appended_rows = _mark_new_rows(new_rows, existing_keys)
    n_deduped = len(new_rows) - len(appended_rows)
    log.info(
        "dedup: %d new rows to append, %d already present (skipped)",
        len(appended_rows), n_deduped,
    )

    # ── determine as_of_today from artifacts ──────────────────────────────
    # Use the most recent as_of seen across loaded artifacts.
    candidate_dates = []
    if exp_data:
        d = exp_data.get("as_of")
        if d:
            candidate_dates.append(d)
    if standouts_data:
        d = standouts_data.get("as_of")
        if d:
            candidate_dates.append(d)
    if rr_data:
        d = rr_data.get("asof")  # note: no underscore
        if d:
            candidate_dates.append(d)
    as_of_today = max(candidate_dates) if candidate_dates else date.today().isoformat()

    # ── build summary over all rows (existing + appended) ─────────────────
    all_rows_for_summary = existing_rows + appended_rows
    summary = _build_summary(all_rows_for_summary, generated_at, as_of_today)

    result = {
        "generated_at": generated_at,
        "as_of": as_of_today,
        "n_new_rows": len(appended_rows),
        "n_existing_rows": len(existing_rows),
        "n_deduped": n_deduped,
        "n_unknown_lanes": n_unknown_lanes_total,
        "summary_n_rows_in_window": summary["n_rows_in_window"],
    }

    if dry_run:
        log.info("[dry-run] would write %d rows to %s", len(appended_rows), log_path)
        log.info("[dry-run] would write summary to data/governance/operator_exposure_summary.json")
        return result

    # ── write exposure_log.jsonl (append-only) ─────────────────────────────
    if appended_rows:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            for row in appended_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        log.info("wrote %d rows to %s", len(appended_rows), log_path)

    # ── write summary JSON (committed) ────────────────────────────────────
    summary_path = root / "data" / "governance" / "operator_exposure_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("wrote summary to %s", summary_path)

    return result


def run_as_collect_step() -> None:
    """End-of-collect hook — must never raise; wraps run() in a broad except."""
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        log.error("[operator_exposure] build step crashed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=None, help="repo root (default: parent of scripts/)")
    ap.add_argument("--dry-run", action="store_true", help="print, no writes")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    root = Path(args.root) if args.root else None
    result = run(root=root, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
