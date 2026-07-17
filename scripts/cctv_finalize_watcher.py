"""CCTV 新闻联播 backfill-finalization watcher — W4/D5 of the Qualitative-Intelligence Upgrade.

Called nightly from scripts/collect.py as a non-fatal end-of-collect step.  Drives a simple
three-state machine that coexists safely with the running backfill process (checkpoint-skip
makes concurrent reads safe) and self-heals stalled scrapes.

State machine (persisted in data/china_news/cctv_archive/finalize_state.json)
------------------------------------------------------------------------------
  SCRAPING   — archive coverage < threshold (default 97 % of 2016-02-03 → today).
               Each collect run checks progress via a fast shard-scan gap audit.
               If the backfill log / shards show NO progress in > 24 h AND no live
               backfill process is detected (pgrep -f backfill_cctv_archive), we
               self-heal by relaunching the detached scrape and firing ONE alert.

  COMPLETE   → FINALIZING — on the first collect run where coverage ≥ threshold.
               Runs scripts/finalize_cctv_backfill.py end-to-end (with --repair).
               On success → FINALIZED.

  FINALIZED  — terminal, idempotent forever.  On the transition collect run:
               · Removes the gitignore line for *.parquet shards so the normal
                 `git add data/` in the nightly workflow picks them up.
               · Fires ONE telegram/discord alert with the full verdict.
               Monthly top-up (mtime-gated): appends new archive days to
               cctv_tone_history.parquet so the 10-year baseline stays live.

Shard-commit mechanics
----------------------
The collect workflow already runs `git add data/` after this step completes.
Transitioning to FINALIZED atomically removes the `.gitignore` shards line so
the next `git add data/` in the SAME nightly run will stage all shard parquets.
The collect job's existing commit ("data: daily collection YYYY-MM-DD") therefore
carries the ~43–60 MB one-time shard payload exactly once.  The FINALIZED marker
prevents the un-gitignore from firing again, so future nightly `git add data/`
calls are normal-sized (only tone_history.parquet deltas).

Usage
-----
  # Called from collect.py:
  from scripts.cctv_finalize_watcher import run_as_collect_step
  run_as_collect_step()

  # Manual / debug:
  python -m scripts.cctv_finalize_watcher [--dry-run] [--force-check]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = REPO_ROOT / "data" / "china_news" / "cctv_archive"
STATE_FILE = ARCHIVE_DIR / "finalize_state.json"
TONE_HISTORY_PATH = REPO_ROOT / "data" / "china_news" / "cctv_tone_history.parquet"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"
BACKFILL_LOG = ARCHIVE_DIR / "backfill.log"
FIRED_STATE_FILE = REPO_ROOT / "data" / "china_news" / "cctv_finalize_alerts_fired.json"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
COVERAGE_THRESHOLD = 0.97      # ≥ 97 % of 2016-02-03 → today dates archived
STALL_HOURS = 24               # hours without log progress → stall declared
GITIGNORE_SHARD_PATTERN = "data/china_news/cctv_archive/*.parquet"
MONTHLY_TOPUP_MIN_AGE_DAYS = 28  # tone_history top-up runs at most monthly

# Alert keys for dedup
_ALERT_STALL = "cctv_scrape_stall"
_ALERT_FINALIZED = "cctv_backfill_finalized"

log = logging.getLogger("cctv_finalize_watcher")

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

_STATE_SCRAPING = "SCRAPING"
_STATE_COMPLETE = "COMPLETE"
_STATE_FINALIZING = "FINALIZING"
_STATE_FINALIZED = "FINALIZED"


def _load_state() -> dict:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"state": _STATE_SCRAPING, "last_check_utc": None, "stall_alert_sent": False}


def _save_state(st: dict) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# Fired-state dedup (one-time alerts)
# ---------------------------------------------------------------------------

def _load_fired() -> dict:
    if FIRED_STATE_FILE.exists():
        try:
            return json.loads(FIRED_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _mark_fired(key: str) -> None:
    fired = _load_fired()
    fired[key] = datetime.now(timezone.utc).isoformat()
    FIRED_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    FIRED_STATE_FILE.write_text(json.dumps(fired, indent=2), encoding="utf-8")


def _already_fired(key: str) -> bool:
    return key in _load_fired()


# ---------------------------------------------------------------------------
# Alert (telegram + discord) — mirrors scripts/notify.py idiom
# ---------------------------------------------------------------------------

def _send_alert(msg: str, dry_run: bool = False) -> None:
    """Fire a plain-text alert to telegram and/or discord. Non-fatal."""
    if dry_run:
        log.info("[dry-run] alert: %s", msg)
        return
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from lib import config  # noqa: PLC0415
        import requests  # noqa: PLC0415

        token = config.secret("TELEGRAM_BOT_TOKEN")
        chat = config.secret("TELEGRAM_CHAT_ID")
        cfg = config.load()
        tg_ok = cfg.get("notify", {}).get("telegram", {}).get("enabled") and token and chat

        if tg_ok:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
                timeout=30,
            )
            if r.status_code == 200:
                log.info("cctv_watcher alert sent via telegram")
            else:
                log.warning("telegram send failed: %s %s", r.status_code, r.text[:200])

        discord_url = config.secret("DISCORD_WEBHOOK_URL")
        dc_ok = cfg.get("notify", {}).get("discord", {}).get("enabled") and discord_url
        if dc_ok:
            plain = msg.replace("<b>", "**").replace("</b>", "**")
            r2 = requests.post(discord_url, json={"content": plain[:1990]}, timeout=30)
            if r2.status_code not in (200, 204):
                log.warning("discord send failed: %s %s", r2.status_code, r2.text[:200])
            else:
                log.info("cctv_watcher alert sent via discord")
    except Exception as e:  # noqa: BLE001
        log.warning("cctv_watcher alert send failed (non-fatal): %s", e)


# ---------------------------------------------------------------------------
# Gap audit (fast — reads only shard headers)
# ---------------------------------------------------------------------------

def _fast_gap_audit(archive_dir: Path) -> dict:
    """Fast coverage check.  Imports backfill_cctv_archive helpers directly.
    Returns dict with: total_dates, total_covered, coverage_pct, is_above_threshold."""
    from scripts.backfill_cctv_archive import (  # noqa: PLC0415
        _all_dates, _already_archived, HISTORY_START,
    )
    dates = _all_dates()
    covered = sum(1 for d in dates if _already_archived(archive_dir, d))
    total = len(dates)
    pct = covered / total if total else 0.0
    return {
        "total_dates": total,
        "total_covered": covered,
        "coverage_pct": pct,
        "is_above_threshold": pct >= COVERAGE_THRESHOLD,
        "history_start": str(HISTORY_START),
        "as_of": str(date.today()),
    }


# ---------------------------------------------------------------------------
# Stall detection
# ---------------------------------------------------------------------------

def _log_mtime_utc(archive_dir: Path) -> datetime | None:
    """Return the most recent mtime across backfill.log and all *.parquet shards."""
    candidates = list(archive_dir.glob("*.parquet"))
    log_path = archive_dir / "backfill.log"
    if log_path.exists():
        candidates.append(log_path)
    if not candidates:
        return None
    latest_mtime = max(p.stat().st_mtime for p in candidates)
    return datetime.fromtimestamp(latest_mtime, tz=timezone.utc)


def _backfill_process_alive() -> bool:
    """True if a backfill_cctv_archive process is currently running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "backfill_cctv_archive"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:  # noqa: BLE001
        return False  # conservative: assume alive on pgrep failure


def _is_stalled(archive_dir: Path) -> bool:
    """True if archive shows no progress in > STALL_HOURS and no process is alive."""
    if _backfill_process_alive():
        return False
    mtime = _log_mtime_utc(archive_dir)
    if mtime is None:
        return False   # no data yet — not stalled, just not started
    age_h = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
    return age_h > STALL_HOURS


# ---------------------------------------------------------------------------
# Self-heal: relaunch detached scrape
# ---------------------------------------------------------------------------

def _relaunch_backfill(archive_dir: Path) -> None:
    """Relaunch the scrape as a detached nohup process (newest → oldest)."""
    log_path = archive_dir / "backfill.log"
    cmd = [
        sys.executable, "-m", "scripts.backfill_cctv_archive",
        "--out-dir", str(archive_dir),
    ]
    log.info("Relaunching CCTV backfill: %s", " ".join(cmd))
    # Detach from the collect process; append to existing log
    with open(log_path, "a") as logf:
        subprocess.Popen(
            cmd,
            stdout=logf,
            stderr=logf,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            cwd=str(REPO_ROOT),
            start_new_session=True,   # detach from caller's process group
        )


# ---------------------------------------------------------------------------
# Gitignore manipulation
# ---------------------------------------------------------------------------

def _remove_gitignore_shard_line(dry_run: bool = False) -> bool:
    """Remove the cctv_archive *.parquet line from .gitignore.
    Returns True if a change was made."""
    if not GITIGNORE_PATH.exists():
        log.warning(".gitignore not found at %s", GITIGNORE_PATH)
        return False

    text = GITIGNORE_PATH.read_text(encoding="utf-8")
    # Remove the single pattern line (plus any immediately-preceding comment block for it)
    lines = text.splitlines(keepends=True)
    new_lines = []
    skip_next_comment = False
    i = 0
    removed = False
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if stripped == GITIGNORE_SHARD_PATTERN:
            # Remove this line; also remove preceding comment block (lines starting with #)
            # that belong to this entry (walk back in new_lines)
            while new_lines and new_lines[-1].lstrip().startswith("#"):
                new_lines.pop()
            removed = True
            i += 1
            continue
        new_lines.append(line)
        i += 1

    if not removed:
        log.info(".gitignore: shard pattern '%s' not found (already removed or never added)",
                 GITIGNORE_SHARD_PATTERN)
        return False

    if dry_run:
        log.info("[dry-run] would remove '%s' from .gitignore", GITIGNORE_SHARD_PATTERN)
        return True

    GITIGNORE_PATH.write_text("".join(new_lines), encoding="utf-8")
    log.info("Removed '%s' from .gitignore — shards will be staged by next `git add data/`",
             GITIGNORE_SHARD_PATTERN)
    return True


# ---------------------------------------------------------------------------
# Monthly tone-history top-up
# ---------------------------------------------------------------------------

def _monthly_topup(archive_dir: Path, dry_run: bool = False) -> None:
    """Append new archive days to cctv_tone_history.parquet (content-gated, monthly).

    The gate reads the parquet's own newest index date — never file mtime.
    The tone history IS versioned once FINALIZED (see the .gitignore note), and
    on CI runners a checkout rewrites committed files with mtime = checkout
    time, so an mtime gate would read perpetually fresh and never top up
    (#2690 class). Unreadable/undated parquet ⇒ treated stale (rebuild — the
    rebuild is an idempotent re-derive from shards, so failing stale is safe).
    """
    if not TONE_HISTORY_PATH.exists():
        log.debug("monthly_topup: tone_history does not exist — skipping")
        return

    age_days: float | None = None
    try:
        import pandas as pd  # noqa: PLC0415 — heavy; only on the top-up path
        idx = pd.to_datetime(
            pd.read_parquet(TONE_HISTORY_PATH, columns=[]).index, errors="coerce"
        ).dropna()
        if len(idx):
            age_days = (pd.Timestamp.now() - idx.max()) / pd.Timedelta(days=1)
    except Exception as e:  # noqa: BLE001
        log.warning("monthly_topup: cannot read tone_history content date (%s) — "
                    "treating as stale", e)

    if age_days is not None and age_days < MONTHLY_TOPUP_MIN_AGE_DAYS:
        log.debug("monthly_topup: tone_history content is %.1f days old — skipping (< %d d)",
                  age_days, MONTHLY_TOPUP_MIN_AGE_DAYS)
        return

    log.info("monthly_topup: tone_history content is %s days old — rebuilding from shards",
             f"{age_days:.1f}" if age_days is not None else "unknown")
    if dry_run:
        log.info("[dry-run] would run rebuild_cctv_tone_history.rebuild()")
        return

    try:
        from scripts.rebuild_cctv_tone_history import rebuild  # noqa: PLC0415
        df = rebuild(archive_dir, TONE_HISTORY_PATH)
        log.info("monthly_topup: rebuilt tone_history — %d rows (%s → %s)",
                 len(df),
                 df.index.min().date() if len(df) else "?",
                 df.index.max().date() if len(df) else "?")
    except Exception as e:  # noqa: BLE001
        log.warning("monthly_topup failed (non-fatal): %s", e)


# ---------------------------------------------------------------------------
# FINALIZED transition actions
# ---------------------------------------------------------------------------

def _do_finalize_transition(
    audit: dict,
    dry_run: bool = False,
) -> None:
    """Executed exactly once when the state machine enters FINALIZED.

    1. Removes the gitignore line for shards (so nightly `git add data/` stages them).
    2. Reads the validation scorecard for the alert payload.
    3. Fires a one-time telegram/discord alert with the full verdict.
    """
    # 1. Un-gitignore the shards
    _remove_gitignore_shard_line(dry_run=dry_run)

    # 2. Read scorecard for alert payload
    scorecard_path = REPO_ROOT / "data" / "china_validation" / "scorecard.json"
    ns: dict = {}
    if scorecard_path.exists():
        try:
            sc = json.loads(scorecard_path.read_text(encoding="utf-8"))
            ns = (sc.get("families") or {}).get("news_sentiment") or {}
        except Exception:
            pass

    cov_pct = round(audit.get("coverage_pct", 0) * 100, 1)
    n_obs = ns.get("n_obs", 0)
    proven = ns.get("proven", False)
    sign_ok = ns.get("sign_ok", None)
    t_hac = ns.get("t_hac")
    mean_ic = ns.get("mean_ic")

    tone_rows = 0
    if TONE_HISTORY_PATH.exists():
        try:
            import pandas as pd  # noqa: PLC0415
            tone_rows = len(pd.read_parquet(TONE_HISTORY_PATH))
        except Exception:
            pass

    leg_verdict = "reactivated" if (proven and sign_ok) else "stays salience-only"
    t_str = f"t_hac={t_hac:.3f}" if t_hac is not None else "t_hac=?"
    ic_str = f"mean_ic={mean_ic:.4f}" if mean_ic is not None else "mean_ic=?"

    msg = (
        f"<b>CCTV backfill FINALIZED</b>: coverage {cov_pct}%, "
        f"tone history {tone_rows:,} days; "
        f"china_validation news_sentiment: n_obs={n_obs}, "
        f"sign={sign_ok}, {t_str}, {ic_str} "
        f"vs contrarian prior → proven={proven}, sign_ok={sign_ok} "
        f"(direction leg <b>{leg_verdict}</b>)"
    )

    log.info("CCTV backfill FINALIZED. Alert: %s", msg)

    if not _already_fired(_ALERT_FINALIZED):
        _send_alert(msg, dry_run=dry_run)
        _mark_fired(_ALERT_FINALIZED)
    else:
        log.debug("finalized alert already sent — skipping")


# ---------------------------------------------------------------------------
# Main state machine
# ---------------------------------------------------------------------------

def run(dry_run: bool = False, force_check: bool = False) -> dict:
    """Drive one step of the CCTV finalization state machine.  Returns a summary dict."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    st = _load_state()
    state = st.get("state", _STATE_SCRAPING)

    now_utc = datetime.now(timezone.utc).isoformat()
    st["last_check_utc"] = now_utc

    # ------------------------------------------------------------------
    # Terminal state — cheap idempotent path
    # ------------------------------------------------------------------
    if state == _STATE_FINALIZED:
        log.debug("CCTV watcher: already FINALIZED — running monthly top-up check")
        _monthly_topup(ARCHIVE_DIR, dry_run=dry_run)
        _save_state(st)
        return {"state": _STATE_FINALIZED, "action": "monthly_topup_check"}

    # ------------------------------------------------------------------
    # SCRAPING — check progress, detect stall, maybe transition
    # ------------------------------------------------------------------
    if state in (_STATE_SCRAPING, _STATE_COMPLETE):
        # Fast coverage check
        try:
            audit = _fast_gap_audit(ARCHIVE_DIR)
        except Exception as e:  # noqa: BLE001
            log.warning("CCTV watcher gap-audit failed (non-fatal): %s", e)
            _save_state(st)
            return {"state": state, "action": "gap_audit_failed", "error": str(e)}

        cov_pct = round(audit["coverage_pct"] * 100, 2)
        log.info("CCTV watcher: state=%s coverage=%s%% (%d/%d dates)",
                 state, cov_pct, audit["total_covered"], audit["total_dates"])
        st["last_coverage_pct"] = cov_pct
        st["last_covered"] = audit["total_covered"]
        st["last_total"] = audit["total_dates"]

        if audit["is_above_threshold"]:
            # Coverage reached — finalize
            log.info("CCTV watcher: coverage %.2f%% ≥ %.0f%% threshold → FINALIZING",
                     cov_pct, COVERAGE_THRESHOLD * 100)
            st["state"] = _STATE_FINALIZING
            _save_state(st)
            return _run_finalize(st, audit, dry_run=dry_run)

        # Still scraping — check for stall
        if _is_stalled(ARCHIVE_DIR):
            log.warning("CCTV watcher: stall detected (no progress > %dh, no live process)",
                        STALL_HOURS)
            st["last_stall_utc"] = now_utc

            if not _already_fired(_ALERT_STALL):
                stall_msg = (
                    "<b>CCTV scrape stalled</b> — no progress in > "
                    f"{STALL_HOURS}h, no live backfill process detected. "
                    f"Coverage: {cov_pct}%. Relaunching automatically."
                )
                _send_alert(stall_msg, dry_run=dry_run)
                _mark_fired(_ALERT_STALL)
            else:
                log.info("Stall already alerted — relaunching silently")

            if not dry_run:
                _relaunch_backfill(ARCHIVE_DIR)
                log.info("CCTV backfill relaunched (detached)")

        _save_state(st)
        return {"state": state, "coverage_pct": cov_pct,
                "action": "stall_relaunch" if _is_stalled(ARCHIVE_DIR) else "watching"}

    # ------------------------------------------------------------------
    # FINALIZING — shouldn't persist across runs, but handle gracefully
    # ------------------------------------------------------------------
    if state == _STATE_FINALIZING:
        log.info("CCTV watcher: state=FINALIZING — re-running finalize pipeline")
        try:
            audit = _fast_gap_audit(ARCHIVE_DIR)
        except Exception:
            audit = {}
        return _run_finalize(st, audit, dry_run=dry_run)

    log.warning("CCTV watcher: unknown state %r — resetting to SCRAPING", state)
    st["state"] = _STATE_SCRAPING
    _save_state(st)
    return {"state": _STATE_SCRAPING, "action": "state_reset"}


def _run_finalize(st: dict, audit: dict, dry_run: bool = False) -> dict:
    """Run scripts/finalize_cctv_backfill.py end-to-end and transition to FINALIZED."""
    log.info("Running finalize_cctv_backfill pipeline (--repair)...")
    try:
        # Import and call the five-stage pipeline functions directly
        from scripts.finalize_cctv_backfill import (  # noqa: PLC0415
            _run_gap_audit as _full_gap_audit,
            run_tone_rebuild,
            shard_commit_decision,
            check_rebaseline,
            run_validation,
        )

        # (a) Full gap audit with repair-list
        full_audit = _full_gap_audit(ARCHIVE_DIR)
        log.info("finalize gap audit: complete=%s missing=%d retriable=%d",
                 full_audit["is_complete"], full_audit["total_missing"],
                 full_audit["total_retriable"])

        # (a2) Repair if there are retriable dates
        if full_audit["total_retriable"] > 0 and not dry_run:
            log.info("Running --repair on %d retriable dates...", full_audit["total_retriable"])
            try:
                from scripts.backfill_cctv_archive import run_backfill  # noqa: PLC0415
                run_backfill(ARCHIVE_DIR, repair=True)
                # Re-audit after repair
                full_audit = _full_gap_audit(ARCHIVE_DIR)
                log.info("Post-repair: complete=%s missing=%d", full_audit["is_complete"],
                         full_audit["total_missing"])
            except Exception as e:  # noqa: BLE001
                log.warning("Repair pass failed (continuing anyway): %s", e)

        # (b) Tone rebuild
        tone_result = run_tone_rebuild(ARCHIVE_DIR, TONE_HISTORY_PATH, dry_run=dry_run)
        log.info("tone rebuild: %s", tone_result)

        # (c) Shard commit decision (logging only — actual staging is via gitignore removal)
        commit_result = shard_commit_decision(ARCHIVE_DIR)
        log.info("shard commit decision: policy=%s size=%.1fMB",
                 commit_result.get("policy"), commit_result.get("total_mb"))

        # (d) Re-baseline
        rebase_result = check_rebaseline(ARCHIVE_DIR)
        log.info("rebaseline: %s", rebase_result.get("status"))

        # (e) Validation re-run
        val_result = run_validation(dry_run=dry_run)
        ns = val_result.get("news_sentiment") or {}
        log.info("validation: proven=%s n_obs=%s sign_ok=%s",
                 ns.get("proven"), ns.get("n_obs"), ns.get("sign_ok"))

        # --- Transition to FINALIZED ---
        st["state"] = _STATE_FINALIZED
        st["finalized_utc"] = datetime.now(timezone.utc).isoformat()
        st["coverage_pct_at_finalize"] = audit.get("coverage_pct") or full_audit.get("coverage_pct")
        st["tone_history_rows"] = tone_result.get("n_rows", 0)
        st["news_sentiment"] = {
            "n_obs": ns.get("n_obs", 0),
            "proven": ns.get("proven", False),
            "sign_ok": ns.get("sign_ok"),
            "t_hac": ns.get("t_hac"),
        }
        _save_state(st)

        # One-time finalized actions (gitignore + alert)
        _do_finalize_transition(audit=full_audit, dry_run=dry_run)

        return {
            "state": _STATE_FINALIZED,
            "action": "finalized",
            "tone_rows": tone_result.get("n_rows", 0),
            "news_sentiment": st["news_sentiment"],
            "shard_policy": commit_result.get("policy"),
        }

    except Exception as e:  # noqa: BLE001
        log.error("finalize pipeline failed (will retry next collect): %s", e)
        # Stay in FINALIZING so next collect run retries
        st["state"] = _STATE_FINALIZING
        st["last_finalize_error"] = str(e)
        st["last_finalize_error_utc"] = datetime.now(timezone.utc).isoformat()
        _save_state(st)
        return {"state": _STATE_FINALIZING, "action": "finalize_error", "error": str(e)}


# ---------------------------------------------------------------------------
# collect.py end-of-collect hook
# ---------------------------------------------------------------------------

def run_as_collect_step(root: Path | str | None = None) -> None:  # noqa: ARG001
    """Called from scripts/collect.py as a non-fatal end-of-collect step.

    Drives one tick of the CCTV finalization state machine.  Never raises.
    """
    try:
        result = run(dry_run=False)
        state = result.get("state", "?")
        action = result.get("action", "")
        cov = result.get("coverage_pct")
        if cov is not None:
            log.info("[cctv_watcher] state=%s coverage=%.1f%% action=%s", state, cov, action)
        else:
            log.info("[cctv_watcher] state=%s action=%s", state, action)
    except Exception as e:  # noqa: BLE001
        log.error("[cctv_watcher] watcher crashed (non-fatal): %s", e)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CCTV finalization watcher (one state-machine tick)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Read-only; print actions without executing writes or alerts")
    ap.add_argument("--force-check", action="store_true",
                    help="Force a full check even if state is FINALIZED")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.force_check:
        # Temporarily reset state for a forced re-check (dry-run only)
        log.info("[force-check] ignoring saved state for this run")
        st = {"state": _STATE_SCRAPING}
        audit = _fast_gap_audit(ARCHIVE_DIR)
        print(json.dumps(audit, indent=2, default=str))
        return 0

    result = run(dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
