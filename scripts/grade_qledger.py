"""scripts/grade_qledger.py — nightly qledger grading job (§2.2 W1-B1).

Desk-independent: loads every open claim from data/qledger/claims.jsonl, grades
each at every in-scope horizon (5/21/63d capped by claim horizon_d) once enough
trading days have elapsed and price coverage exists, then writes the result to
data/qledger/grades.jsonl and updates site/qledger/track_record.json.

IDEMPOTENT: a (claim_id, horizon_d) pair that already has a grade row is never
double-graded. Re-running the job on the same day is safe.

HEALTH: always emits a one-line summary to stdout and writes
data/qledger/run_status.json — broken != quiet.

POST-STEP — W6 PROMOTION-READINESS MONITOR:
    After emit_ladder_states(), compute_promotion_readiness() runs for every
    claim family listed in config/qual_ladder.yml. It writes:
      • site/qledger/track_record.json["promotion_readiness"] — per family×horizon
        {n_dates, needed:25, wilson_ci_low, hit_rate, excess_mean, ready, approaching,
         projected_ready_date}.
      • data/qledger/run_status.json["w6_readiness"] — summary (n_families_ready,
        n_families_approaching, families_ready[]).
    On first-cross ready=True for any family, a Telegram/Discord alert fires once
    (fired state persisted in data/qledger/readiness_alerts_fired.json so it does
    not re-fire nightly). A grader-quiet alert fires if n_graded_today==0 for two
    consecutive days when open claims exist (checked in the summary as
    grader_quiet_days).

WIRING (end-of-collect hook):
    The job is registered as an end-of-collect step in scripts/collect.py, so it
    runs nightly as part of the collection pipeline without a separate scheduler.
    It is also runnable standalone:

        python scripts/grade_qledger.py            # use repo root
        python scripts/grade_qledger.py --root /other/root
        python scripts/grade_qledger.py --dry-run  # compute only, no writes

PRICE FALLBACK ORDER (reusing engine.ai_desk._close_series):
  1. data/yahoo/<ticker>.parquet  — ~153 major names, SPY/XL* etc.
  2. S&P-1500 breadth-cache       — wider coverage for entity claims
  3. data/baskets/ohlcv/<ticker>.parquet — per-member basket OHLCV
  4. 510300.SS parquet            — CN macro bench (via breadth cache or yahoo)

If subject OR bench price is unavailable the horizon is counted in
n_blocked_by_coverage (not silently dropped) and the run_status records it.
Ungradeable claims (EVENT_DATE/SNAPSHOT_DATE timestamp_quality) are counted in
n_ungradeable.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Allow running as a top-level script (`python scripts/grade_qledger.py`).
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import qledger as q
from lib import config

log = logging.getLogger("grade_qledger")

_STATUS_FILE = ("data", "qledger", "run_status.json")
_READINESS_FIRED_FILE = ("data", "qledger", "readiness_alerts_fired.json")
_QUIET_LOG_FILE = ("data", "qledger", "grader_quiet_log.json")

# ──────────────────────────────────────────────────────────────────────────────
# W6 READINESS HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _load_qual_ladder_families(root: Path) -> list[str]:
    """Parse config/qual_ladder.yml to extract the authoritative set of
    claim_family values. Returns them sorted and deduplicated.
    Falls back to an empty list if the file is absent or unparseable (non-fatal).
    """
    yml_path = root / "config" / "qual_ladder.yml"
    if not yml_path.exists():
        return []
    families: set[str] = set()
    try:
        text = yml_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("claim_family:"):
                val = line.split(":", 1)[1].strip()
                if val and not val.startswith("#"):
                    families.add(val)
    except Exception as e:  # noqa: BLE001
        log.warning("_load_qual_ladder_families: failed to parse qual_ladder.yml: %s", e)
    return sorted(families)


def _accrual_rate_per_day(grades: list[dict], claims: list[dict],
                          family: str, horizon: int,
                          trailing_days: int = 14) -> float | None:
    """Estimate the rate of NEW independent date clusters accruing per calendar day
    over the trailing `trailing_days` window. Returns None when insufficient data.
    Used for projected_ready_date linear extrapolation.
    """
    cid_meta = {
        c["claim_id"]: c for c in claims
        if c.get("claim_id") and (c.get("claim_family") or c.get("desk")) == family
        and not c.get("is_placebo")
    }
    if not cid_meta:
        return None

    today_dt = date.today()
    cutoff = datetime(today_dt.year, today_dt.month, today_dt.day,
                      tzinfo=timezone.utc) - __import__("datetime").timedelta(days=trailing_days)

    recent_dates: set[str] = set()
    for g in grades:
        if int(g.get("horizon_d", -1)) != horizon:
            continue
        c = cid_meta.get(g.get("claim_id"))
        if c is None:
            continue
        graded_at = g.get("graded_at", "")
        try:
            gts = datetime.fromisoformat(graded_at)
            if gts >= cutoff:
                recent_dates.add(q._date_cluster(c.get("asof", "")))
        except Exception:  # noqa: BLE001
            continue

    if not recent_dates:
        return None
    rate = len(recent_dates) / trailing_days   # dates / calendar-day
    return rate if rate > 0 else None


def _projected_ready_date(n_dates: int, rate_per_day: float | None) -> str | None:
    """Linear projection: days_needed / rate → ISO date. Returns None when rate ~0."""
    needed = q.PROMOTION_MIN_DATES - n_dates
    if needed <= 0 or rate_per_day is None or rate_per_day < 1e-6:
        return None
    days = math.ceil(needed / rate_per_day)
    from datetime import timedelta
    proj = date.today() + timedelta(days=days)
    return proj.isoformat()


def compute_promotion_readiness(root: Path, families: list[str] | None = None) -> dict:
    """Compute W6 promotion-readiness metrics for each claim family × grade horizon.

    For each (family, horizon):
      - n_dates:              independent date clusters graded so far
      - needed:               25 (PROMOTION_MIN_DATES constant)
      - wilson_ci_low:        Wilson CI lower bound (None if no directional grades)
      - hit_rate:             directional hit-rate (None if salience-only)
      - excess_mean:          mean excess return (None if no grades)
      - ready:                n_dates>=25 AND wilson_ci_low>0 (§3 gate)
      - approaching:          n_dates>=20 AND not ready (5-date warning window)
      - projected_ready_date: linear estimate from trailing-14d accrual rate (or None)

    Placebo tape duel summary per horizon (duel_context):
      champion vs challenger vs placebo |excess| at 5d — the key decision evidence
      for the human reviewer in the admin Experiments tab.

    Returns a dict: {family: {horizon_str: {…}, …}, "_duel_context": {…}}
    """
    root = Path(root)
    claims = q.load_claims(root)
    grades = q.load_grades(root)

    if families is None:
        families = _load_qual_ladder_families(root)

    result: dict[str, dict] = {}
    for fam in families:
        fam_res: dict[str, dict] = {}
        for h in q.GRADE_HORIZONS:
            pr = q.promotion_check(fam, h, root=root, control_only=True)
            rate = _accrual_rate_per_day(grades, claims, fam, h)
            proj = _projected_ready_date(pr.n_dates, rate)
            approaching = (pr.n_dates >= 20 and not pr.eligible)

            # hit_rate and excess_mean from track record aggregation
            stats = q._aggregate(claims, grades, "family", h)
            fam_stats = stats.get(fam, {})

            fam_res[str(h)] = {
                "n_dates": pr.n_dates,
                "needed": q.PROMOTION_MIN_DATES,
                "wilson_ci_low": pr.wilson_ci_low,
                "hit_rate": fam_stats.get("hit_rate"),
                "excess_mean": fam_stats.get("excess_mean"),
                "ready": pr.eligible,
                "approaching": approaching,
                "projected_ready_date": proj,
                "reason": pr.reason,
            }
        result[fam] = fam_res

    # Duel context: champion vs placebo |excess| at 5d from the track record
    # This is the key decision evidence visible in the admin Experiments tab.
    duel_context: dict[str, dict] = {}
    tr_path = root.joinpath(*q._TRACK_FILE)
    try:
        tr = json.loads(tr_path.read_text(encoding="utf-8")) if tr_path.exists() else {}
        placebo = (tr.get("placebo_magnitude") or {}).get("5", {})
        placebo_covered = (placebo.get("covered_ticker") or {}).get("mean_abs_excess")
        by_family = tr.get("by_family") or {}
        for fam in families:
            h5 = (by_family.get(fam) or {}).get("5") or {}
            duel_context[fam] = {
                "challenger_excess_mean_5d": h5.get("excess_mean"),
                "placebo_covered_abs_excess_5d": placebo_covered,
                "n_dates_5d": h5.get("n_dates", 0),
                "wilson_ci_low_5d": h5.get("wilson_ci_low"),
            }
    except Exception as e:  # noqa: BLE001
        log.debug("compute_promotion_readiness: duel_context build failed: %s", e)

    result["_duel_context"] = duel_context
    return result


def _load_fired(root: Path) -> dict:
    p = root.joinpath(*_READINESS_FIRED_FILE)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_fired(root: Path, fired: dict) -> None:
    p = root.joinpath(*_READINESS_FIRED_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fired, ensure_ascii=False, indent=2), encoding="utf-8")


def _fire_readiness_alert(family: str, horizon: int, rec: dict) -> None:
    """Send Telegram+Discord alert for a first-cross ready=True. Non-fatal."""
    msg = (
        f"🔔 <b>W6 gate OPEN: {family} @ {horizon}d</b>\n"
        f"n_dates={rec['n_dates']}, CI-low={rec['wilson_ci_low']}\n"
        f"§3 promotion experiment runnable — see "
        f"QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md §4 W6\n"
        f"→ admin Experiments tab: https://admin.mastermind-x.com"
    )
    try:
        from scripts import notify
        notify.send_telegram(msg)
        notify.send_discord(msg)
        log.info("readiness alert fired: family=%s horizon=%d", family, horizon)
    except Exception as e:  # noqa: BLE001
        log.warning("readiness alert send failed: %s", e)


def _fire_grader_quiet_alert(n_open: int, quiet_days: int) -> None:
    """Send a warn-level alert when the grader has been quiet for quiet_days
    while open claims exist. Non-fatal."""
    msg = (
        f"⚠️ <b>qledger grader quiet {quiet_days}d</b>\n"
        f"n_graded_today=0 for {quiet_days} consecutive days with {n_open} open claims.\n"
        f"Broken ≠ quiet — check scripts/grade_qledger.py and data/qledger/run_status.json."
    )
    try:
        from scripts import notify
        notify.send_telegram(msg)
        notify.send_discord(msg)
        log.warning("grader-quiet alert fired: quiet_days=%d n_open=%d", quiet_days, n_open)
    except Exception as e:  # noqa: BLE001
        log.warning("grader-quiet alert send failed: %s", e)


def _update_grader_quiet_log(root: Path, n_graded_today: int, n_open: int) -> int:
    """Track consecutive days of n_graded_today==0 with open claims.
    Returns the current consecutive_quiet_days count. Updates the log file."""
    p = root.joinpath(*_QUIET_LOG_FILE)
    today = date.today().isoformat()
    try:
        state = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:  # noqa: BLE001
        state = {}

    if n_graded_today == 0 and n_open > 0:
        # Accumulate quiet days; avoid double-counting same calendar day
        last_quiet_date = state.get("last_quiet_date")
        if last_quiet_date == today:
            # Already counted today — no change
            return state.get("consecutive_quiet_days", 1)
        state["consecutive_quiet_days"] = state.get("consecutive_quiet_days", 0) + 1
        state["last_quiet_date"] = today
    else:
        state["consecutive_quiet_days"] = 0
        state["last_quiet_date"] = today

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.debug("_update_grader_quiet_log write failed: %s", e)
    return state.get("consecutive_quiet_days", 0)


def run_readiness_post_step(root: Path, n_graded_today: int, n_open: int,
                             dry_run: bool = False) -> dict:
    """W6 promotion-readiness post-step. Called after emit_ladder_states().

    1. Computes per-family×horizon readiness metrics.
    2. Merges them into site/qledger/track_record.json["promotion_readiness"].
    3. Returns a summary dict for inclusion in run_status.json["w6_readiness"].
    4. Fires first-cross Telegram/Discord alerts (deduped via readiness_alerts_fired.json).
    5. Checks grader-quiet condition (n_graded_today==0 for >=2 days with open claims).

    Non-fatal — any crash returns an error summary without affecting grades.
    """
    try:
        families = _load_qual_ladder_families(root)
        readiness = compute_promotion_readiness(root, families)

        # Merge into track_record.json
        if not dry_run:
            tr_path = root.joinpath(*q._TRACK_FILE)
            try:
                payload: dict = json.loads(tr_path.read_text(encoding="utf-8")) \
                    if tr_path.exists() else {}
            except Exception:  # noqa: BLE001
                payload = {}
            payload["promotion_readiness"] = readiness
            payload["promotion_readiness_at"] = datetime.now(timezone.utc).isoformat()
            tr_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                               encoding="utf-8")

        # Summary for run_status.json
        families_ready = []
        families_approaching = []
        for fam, horizons in readiness.items():
            if fam.startswith("_"):
                continue
            for h_str, rec in horizons.items():
                if rec.get("ready"):
                    families_ready.append(f"{fam}@{h_str}d")
                elif rec.get("approaching"):
                    families_approaching.append(f"{fam}@{h_str}d")

        # First-cross alert (deduped)
        if not dry_run:
            fired = _load_fired(root)
            newly_fired = False
            for fam, horizons in readiness.items():
                if fam.startswith("_"):
                    continue
                for h_str, rec in horizons.items():
                    key = f"{fam}@{h_str}d"
                    if rec.get("ready") and not fired.get(key):
                        _fire_readiness_alert(fam, int(h_str), rec)
                        fired[key] = {
                            "fired_at": datetime.now(timezone.utc).isoformat(),
                            "n_dates": rec["n_dates"],
                            "wilson_ci_low": rec["wilson_ci_low"],
                        }
                        newly_fired = True
            if newly_fired:
                _save_fired(root, fired)

        # Grader-quiet check
        quiet_days = 0
        if not dry_run:
            quiet_days = _update_grader_quiet_log(root, n_graded_today, n_open)
            if quiet_days >= 2:
                # Only alert once per quiet episode (use fired map as dedup)
                fired = _load_fired(root)
                alert_key = f"__grader_quiet_{date.today().isoformat()}"
                if not fired.get(alert_key):
                    _fire_grader_quiet_alert(n_open, quiet_days)
                    fired[alert_key] = {"fired_at": datetime.now(timezone.utc).isoformat(),
                                        "quiet_days": quiet_days}
                    _save_fired(root, fired)

        return {
            "n_families_ready": len(families_ready),
            "n_families_approaching": len(families_approaching),
            "families_ready": families_ready,
            "families_approaching": families_approaching,
            "grader_quiet_days": quiet_days,
        }

    except Exception as e:  # noqa: BLE001
        log.warning("run_readiness_post_step failed (non-fatal): %s", e)
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# idempotency helper
# --------------------------------------------------------------------------- #
def _existing_grade_keys(root: Path) -> set[tuple]:
    """Set of (claim_id, horizon_d) pairs already written to grades.jsonl."""
    return {
        (g.get("claim_id"), int(g.get("horizon_d", -1)))
        for g in q.load_grades(root)
        if g.get("claim_id") is not None
    }


# --------------------------------------------------------------------------- #
# main grader
# --------------------------------------------------------------------------- #
def run(root: Path | str | None = None, today: date | None = None,
        dry_run: bool = False) -> dict:
    """Grade all open claims, write grades + track_record, return a summary dict.

    Parameters
    ----------
    root    : repo root (defaults to lib.config.ROOT).
    today   : reference date for maturity check (defaults to date.today()).
    dry_run : compute grades but do NOT write any files.

    Returns
    -------
    dict with keys: n_open, n_graded_today, n_blocked_by_coverage,
                    n_ungradeable, n_already_graded, generated_at.
    """
    root = Path(root) if root else config.ROOT
    today_dt = today or date.today()

    claims = q.load_claims(root)
    open_claims = [c for c in claims if c.get("status") == q.STATUS_OPEN]
    existing_keys = _existing_grade_keys(root)

    grades_p = root.joinpath(*q._GRADES_FILE)
    if not dry_run:
        grades_p.parent.mkdir(parents=True, exist_ok=True)

    n_open = len(open_claims)
    n_graded_today = 0
    n_blocked_by_coverage = 0
    n_ungradeable = 0
    n_already_graded = 0

    # Collect new grade rows; we'll write them in a single pass.
    new_rows: list[dict] = []

    for claim in open_claims:
        cid = claim.get("claim_id")

        # Check gradeable at all (timestamp_quality gate).
        gradeable, _ = q._embargo_ok(claim)
        if not gradeable:
            n_ungradeable += 1
            continue

        scope = claim.get("scope") or {}
        subject = scope.get("key")
        bench = claim.get("bench") or q._DEFAULT_BENCH
        control = claim.get("control")
        start = q._entry_date(claim)

        try:
            horizon_d = int(claim.get("horizon_d"))
        except Exception:  # noqa: BLE001
            n_ungradeable += 1
            continue

        for h in q.in_scope_horizons(horizon_d):
            key = (cid, h)
            if key in existing_keys:
                n_already_graded += 1
                continue

            legs = [subject, bench] + ([control] if control else [])
            if not q._matured(root, start, h, today_dt, legs):
                # Not yet elapsed or price not yet available — count as blocked.
                n_blocked_by_coverage += 1
                continue

            # grade_claim handles all the price maths; we filter to this horizon.
            rows = q.grade_claim(claim, root=root, today=today_dt)
            matched = [r for r in rows if int(r.get("horizon_d", -1)) == h]

            if matched:
                new_rows.extend(matched)
                n_graded_today += len(matched)
            else:
                # Matured but prices unavailable → coverage miss.
                n_blocked_by_coverage += 1

    # Write grades (append-only).
    if new_rows and not dry_run:
        with grades_p.open("a", encoding="utf-8") as fh:
            for row in new_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Recompute and emit track_record.json, then overlay the §3 promotion-ladder
    # verdicts (per claim_family × horizon) so the ladder state is always current
    # alongside the grade stats. emit_ladder_states merges into the file written by
    # emit_track_record. Non-fatal: a ladder-emit crash must not lose the grades.
    if not dry_run:
        q.emit_track_record(root)
        try:
            q.emit_ladder_states(root)
        except Exception as e:  # noqa: BLE001
            log.warning("emit_ladder_states failed (non-fatal): %s", e)

    # W6 post-step: promotion-readiness monitor (alerts + registry sync).
    # Non-fatal: a crash here must not affect run_status output.
    w6_readiness: dict = {}
    if not dry_run:
        try:
            w6_readiness = run_readiness_post_step(
                root, n_graded_today=n_graded_today, n_open=n_open, dry_run=dry_run
            )
        except Exception as e:  # noqa: BLE001
            log.warning("run_readiness_post_step failed (non-fatal): %s", e)
            w6_readiness = {"error": str(e)}

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": today_dt.isoformat(),
        "n_open": n_open,
        "n_graded_today": n_graded_today,
        "n_blocked_by_coverage": n_blocked_by_coverage,
        "n_ungradeable": n_ungradeable,
        "n_already_graded": n_already_graded,
        "dry_run": dry_run,
        "w6_readiness": w6_readiness,
    }

    # Write run_status.json — broken != quiet.
    if not dry_run:
        status_p = root.joinpath(*_STATUS_FILE)
        status_p.parent.mkdir(parents=True, exist_ok=True)
        status_p.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    msg = (
        f"[grade_qledger] open={n_open} graded_today={n_graded_today} "
        f"blocked={n_blocked_by_coverage} ungradeable={n_ungradeable} "
        f"already_graded={n_already_graded}"
        + (" [DRY RUN]" if dry_run else "")
    )
    log.info(msg)
    print(msg, flush=True)

    return summary


# --------------------------------------------------------------------------- #
# collect.py end-of-collect hook
# --------------------------------------------------------------------------- #
def run_as_collect_step(root: Path | str | None = None) -> None:
    """Called from scripts/collect.py as an end-of-collect step. Non-fatal:
    a grader crash must not abort the nightly collection run."""
    try:
        run(root=root)
    except Exception as exc:  # noqa: BLE001
        log.error("[grade_qledger] grader crashed (non-fatal): %s", exc)


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #
def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Nightly qledger claim grader — grades open claims and "
                    "emits site/qledger/track_record.json.")
    p.add_argument("--root", default=None,
                   help="Repo root (default: lib.config.ROOT).")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute grades but do not write any files.")
    p.add_argument("--today", default=None,
                   help="Override today's date (YYYY-MM-DD) for back-testing.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    today_dt = date.fromisoformat(args.today) if args.today else None
    run(root=args.root, today=today_dt, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
