"""Options accrual freshness tripwire (dead-man's switch for OI + flow accrual).

OI is point-in-time only — every missed snapshot day is permanently lost. This
audit is the circuit-breaker visibility layer described in the Options Alpha
masterplan §W0.4: if the chains/ directory hasn't been updated within 1 NYSE
session, emit a ::warning:: so the CI run surfaces the gap.

Staleness is measured in SESSIONS against the last COMPLETED session, using
lib.nyse_calendar — never in calendar days against today's UTC date. See
_last_trading_day for the three defects that cost (the short version: this
tripwire had the same UTC-run-date bug as the accrual it watches).

Also checks that the options-flow S3 creds are present (MASSIVE_S3_ACCESS_KEY_ID),
since a missing-creds failure in build_options_flow is otherwise a silent no-op.

Writes data/quality/options_accrual_audit.json (observability; read-only over stores).
Stdlib + pandas only — no heavy deps.

Usage: python -m scripts.audit_options_accrual [--strict] [--max-age-sessions 1]
       --strict: exit 1 on stale (default: warn + exit 0)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, nyse_calendar  # noqa: E402

DEFAULT_MAX_AGE_SESSIONS = 1   # chains/ latest file must be ≤ 1 NYSE session behind


def _last_trading_day(ref: date | None = None) -> date:
    """Most recent NYSE session on or before `ref`; `ref=None` means "right now".

    THE REFERENCE IS A SESSION, NOT A UTC CALENDAR DATE (2026-08-06 repair). This
    tripwire used to roll back from ``datetime.now(timezone.utc).date()`` over a
    hand-rolled Mon–Fri-minus-three-holidays calendar. Three defects, measured:

      * The same UTC-midnight bug this tripwire exists to catch. Evaluated at 00:38Z
        on 2026-08-07 — i.e. 20:38 ET on 08-06 — it returned **2026-08-07**, a session
        that had not started, and reported the store 8 sessions behind when the honest
        figure was 5. The watchman ran the same broken clock as the thing it watched.
      * The holiday set held only New Year / July 4 / Christmas, so MLK, Presidents Day,
        Good Friday, Memorial Day, **Juneteenth**, Labor Day and Thanksgiving each read
        as trading days and raised a false STALE. 2026-06-19 (Juneteenth) and 2026-07-03
        (Independence Day observed) both sit inside this very store's window.
      * The age it fed was ``(last_td - latest).days`` — CALENDAR days, printed and
        thresholded as "trading day(s)", so a plain Friday→Monday gap of one session
        read as three.

    ``expected_last_session`` carries a 17:00 ET settle buffer, so between the 16:00 ET
    close and that night's accrual the store is legitimately one session behind — which
    is why the default threshold tolerates exactly 1 and only fails at 2.
    """
    if ref is None:
        return nyse_calendar.expected_last_session()
    return nyse_calendar.last_session_on_or_before(ref)


def _sessions_behind(latest: date, last_td: date) -> int:
    """NYSE sessions strictly after `latest`, up to and including `last_td`.

    Mirrors ``nyse_calendar.sessions_behind`` but takes the reference explicitly, so the
    ``_last_trading_day`` seam the tests monkeypatch still governs the comparison. A
    store somehow ahead of the calendar clamps to 0 rather than going negative."""
    return len(nyse_calendar.sessions_between(latest + timedelta(days=1), last_td))


def _latest_dated_file(paths: list[str]) -> date | None:
    """The most recent YYYY-MM-DD-stemmed file among `paths` (lexically
    sorted), skipping any stray file whose stem does NOT parse as a date
    instead of giving up entirely.

    N8 (AD-1C0 round 2): the pre-fix version took ONLY the lexically-LAST
    path and returned None outright if THAT ONE stem failed to parse — a
    single stray non-date file (a leftover backup, a README, anything that
    happens to sort after every real "YYYY-MM-DD.json"/".parquet" name)
    silently disabled the freshness check entirely, masking every real date
    behind it. Walk backward from the end instead, skipping unparseable
    stems, until a real date is found or the list is exhausted."""
    for p in reversed(paths):
        stem = Path(p).stem
        try:
            return datetime.strptime(stem, "%Y-%m-%d").date()
        except ValueError:
            continue
    return None


def _latest_chain_date(chains_dir: Path) -> date | None:
    """Date of the most recent chains/*.parquet file, or None if no files."""
    return _latest_dated_file(sorted(glob.glob(str(chains_dir / "*.parquet"))))


def _health_receipt_dir(data_root: Path) -> Path:
    # SIBLING of data/polygon_gex/, not nested inside it — see
    # scripts.build_polygon_gex._health_dir()'s docstring for why (a nested
    # subdirectory there breaks tests/test_polygon_gex_session_stamps.py's
    # stray-file invariant). NOT the same function as build_polygon_gex's own
    # _health_dir() (which also mkdir()s it as a writer) — the audit is
    # read-only over this directory and must never create it.
    return data_root / "polygon_gex_health"


def _latest_receipt_date(health_dir: Path) -> date | None:
    """Date of the most recent polygon_gex_health/*.json receipt, or None if
    none exist. Mirrors _latest_chain_date (both route through
    _latest_dated_file — N8: a stray non-date .json sibling must not disable
    this the way it used to). The ``*.json`` glob does not match a preserved
    corrupt-aside file (B3's ``<session>.json.corrupt-<ts>`` does not end in
    ``.json``), so a corrupted-and-recovered session is read from its FRESH
    recovery receipt, not the quarantined original."""
    return _latest_dated_file(sorted(glob.glob(str(health_dir / "*.json"))))


def _read_receipt_attempts(health_dir: Path, session: date) -> list[dict] | None:
    receipt_path = health_dir / f"{session.isoformat()}.json"
    if not receipt_path.exists():
        return None
    try:
        data = json.loads(receipt_path.read_text())
    except (OSError, ValueError):
        return None
    attempts = data.get("attempts") if isinstance(data, dict) else None
    return attempts if isinstance(attempts, list) else None


def _latest_chain_health(health_dir: Path, chains_dir: Path,
                         session: date | None) -> dict | None:
    """AD-1C0: the health-receipt entry describing the CURRENT authoritative
    state of `session`'s stored chain — or None when no receipt exists (a
    legacy session, or the sidecar is simply absent on this runner). Read-only;
    never raises into the audit.

    M12 (AD-1C0 review): reads through
    ``scripts.build_polygon_gex._stored_state_entry`` — the SAME anchor lookup
    accrue() itself uses — rather than blindly taking the literal last attempt.
    A force-run whose capture totally failed against an otherwise-INTACT store
    appends a "nothing_captured"/health="failed" attempt describing that
    REJECTED attempt, not the store; reading the literal last entry would then
    misreport a perfectly healthy, untouched store as failed. _stored_state_entry
    skips every non-anchor (skip-shaped) decision by construction.

    W1 (AD-1C0 round 3): passes the session's own chain parquet path through
    so a trailing write_pending anchor is VERIFIED against the actual on-disk
    file (same as accrue() itself) rather than trusted at face value — the
    audit must never report a phantom capture's health as real.
    """
    if session is None:
        return None
    try:
        from scripts.build_polygon_gex import _stored_state_entry
    except ImportError:  # pragma: no cover — defensive; keeps the audit alive
        return None
    attempts = _read_receipt_attempts(health_dir, session)
    chain_path = chains_dir / f"{session.isoformat()}.parquet"
    return _stored_state_entry(attempts, chain_path)


def audit(max_age_sessions: int = DEFAULT_MAX_AGE_SESSIONS) -> dict:
    """Return {ok, fail_reasons, warnings, detail}."""
    data_root = config.data_dir()
    chains_dir = data_root / "polygon_gex" / "chains"
    today_utc = datetime.now(timezone.utc).date()
    # No argument: the reference is the last COMPLETED session, never today's UTC date
    # (see _last_trading_day — passing today_utc here is what returned an unstarted
    # session and inflated the reported gap).
    last_td = _last_trading_day()

    fail: list[str] = []
    warn: list[str] = []
    detail: dict = {
        "today_utc": str(today_utc),
        "last_trading_day": str(last_td),
        "chains_dir": str(chains_dir),
    }

    # ── chains/ freshness ────────────────────────────────────────────────────
    latest = _latest_chain_date(chains_dir)
    detail["chains_latest_date"] = str(latest) if latest else None
    detail["chains_count"] = len(glob.glob(str(chains_dir / "*.parquet")))

    if latest is None:
        fail.append("CHAINS DARK: data/polygon_gex/chains/ has no parquet files — "
                    "polygon_gex collector has never run or the store is missing")
    else:
        age = _sessions_behind(latest, last_td)
        detail["chains_age_sessions"] = age
        if age > max_age_sessions:
            fail.append(
                f"CHAINS STALE: latest chain file is {latest} "
                f"({age} NYSE session(s) behind last_session={last_td}); "
                f"threshold={max_age_sessions} — OI snapshot may have been missed"
            )
        elif age == max_age_sessions:
            warn.append(
                f"CHAINS AT LIMIT: latest chain file is {latest} "
                f"(exactly {age} NYSE session(s) behind last_session={last_td}) — "
                "expected between the close and that night's accrual, but will trip "
                "if tonight's accrual is missed"
            )

    # ── M4 (AD-1C0 review): a totally-failed newest session is invisible if we
    # only ever glob chains/*.parquet — a session whose accrual captured NOTHING
    # (B2's universe-resolution-failed gate, or a plain zero-capture run) never
    # writes a parquet at all, so the freshness check above silently looks past
    # it and reports whatever the PRIOR successful session's age happens to be.
    # The effective reference is max(newest parquet session, newest receipt
    # session); when the receipt is newer and has no matching parquet, that is
    # its own FAILED finding, independent of the age computation above (which
    # would otherwise see age=0 against the wrong file and call it healthy).
    health_dir = _health_receipt_dir(data_root)
    latest_receipt_session = _latest_receipt_date(health_dir)
    detail["health_latest_receipt_session"] = (
        str(latest_receipt_session) if latest_receipt_session else None)
    if latest_receipt_session is not None and (latest is None or latest_receipt_session > latest):
        fail.append(
            f"CHAINS SESSION FAILED: session {latest_receipt_session} has a health-receipt "
            f"attempt but NO chain parquet was ever written for it — the accrual captured "
            f"nothing for the most recently attempted session (see "
            f"data/polygon_gex_health/{latest_receipt_session.isoformat()}.json)"
        )

    # ── AD-1C0: surface the latest STORED session's health-receipt verdict ───
    latest_health_entry = _latest_chain_health(health_dir, chains_dir, latest)
    if latest_health_entry is not None:
        health = latest_health_entry.get("health")
        detail["chains_latest_health"] = health
        detail["chains_latest_decision"] = latest_health_entry.get("decision")
        detail["chains_latest_coverage_pct"] = latest_health_entry.get("coverage_pct")
        if health in ("partial", "failed"):
            warn.append(
                f"CHAINS {str(health).upper()}: latest chain session {latest} captured "
                f"coverage_pct={latest_health_entry.get('coverage_pct')} "
                f"(failure_reasons={latest_health_entry.get('failure_reasons')}) — see "
                f"data/polygon_gex_health/{latest.isoformat()}.json for the full census"
            )
        elif health == "unknown_receipt_corrupt":
            # N6 (AD-1C0 round 2): B3's corruption-recovery state was
            # previously silent here — the audit surfaced "partial"/"failed"
            # but said nothing when a receipt had been corrupt-and-recovered,
            # even though "unknown" health is exactly the kind of gap a
            # dead-man's-switch tripwire exists to name.
            warn.append(
                f"CHAINS HEALTH UNKNOWN: latest chain session {latest} was recovered "
                f"from a CORRUPT health receipt — its true capture quality is unknown "
                f"(PIT-protected as immutable, never retro-replaced) — see "
                f"data/polygon_gex_health/{latest.isoformat()}.json and any "
                f"*.corrupt-* sibling for the preserved original"
            )
        elif health == "unknown_write_interrupted":
            # W1 (AD-1C0 round 3): a trailing write_pending receipt entry
            # whose on-disk parquet failed verification (mismatched or
            # unreadable) — the write was interrupted (crash, ENOSPC, kill)
            # and the entry's claimed health can no longer be trusted.
            warn.append(
                f"CHAINS HEALTH UNKNOWN: latest chain session {latest} has a stored "
                f"capture whose write was INTERRUPTED — its receipt entry did not "
                f"verify against the parquet on disk (replaceable by a same-day "
                f"re-fetch, not immutable) — see "
                f"data/polygon_gex_health/{latest.isoformat()}.json"
            )

    # ── options-flow S3 creds ────────────────────────────────────────────────
    ak = os.environ.get("MASSIVE_S3_ACCESS_KEY_ID", "")
    sk = os.environ.get("MASSIVE_S3_SECRET_ACCESS_KEY", "")
    ep = os.environ.get("MASSIVE_S3_ENDPOINT", "")
    creds_ok = bool(ak and sk and ep)
    detail["options_flow_creds_present"] = creds_ok
    if not creds_ok:
        warn.append(
            "OPTIONS FLOW CREDS ABSENT: MASSIVE_S3_ACCESS_KEY_ID / "
            "MASSIVE_S3_SECRET_ACCESS_KEY / MASSIVE_S3_ENDPOINT not set — "
            "build_options_flow will no-op silently (F1 from masterplan §1)"
        )

    # ── options-flow summary accrual ─────────────��───────────────────────────
    flow_dir = data_root / "options_flow"
    flow_files = list(flow_dir.glob("summary_*.parquet")) if flow_dir.exists() else []
    detail["options_flow_summary_count"] = len(flow_files)
    if creds_ok and not flow_files:
        warn.append(
            "OPTIONS FLOW SUMMARIES ABSENT: creds are present but "
            "data/options_flow/summary_*.parquet is empty — "
            "build_options_flow may not have run yet"
        )

    return {"ok": not fail, "fail_reasons": fail, "warnings": warn, "detail": detail}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on any STALE/DARK finding (default: report-only)")
    ap.add_argument("--max-age-sessions", "--max-age-days", type=int,
                    dest="max_age_sessions", default=DEFAULT_MAX_AGE_SESSIONS,
                    help="max NYSE sessions behind the last completed session before "
                         f"STALE (default: {DEFAULT_MAX_AGE_SESSIONS}). --max-age-days "
                         "is a back-compat alias; the unit was always meant to be "
                         "sessions and the old code counted calendar days.")
    args = ap.parse_args()

    report = audit(max_age_sessions=args.max_age_sessions)

    # Write observability artifact (non-fatal if it fails)
    try:
        out_dir = config.data_dir() / "quality"
        out_dir.mkdir(parents=True, exist_ok=True)
        doc = {"generated_at": datetime.now(timezone.utc).isoformat(), **report}
        (out_dir / "options_accrual_audit.json").write_text(json.dumps(doc, indent=2) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"::warning::options_accrual_audit: could not write audit json: {e}")

    for w in report["warnings"]:
        print(f"::warning::{w}")
    if report["ok"]:
        print("Options accrual OK")
    for f in report["fail_reasons"]:
        print(f"::error::{f}")
    if not report["ok"] and args.strict:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Collect step hook (W-OC wiring — NEXT3 PR-β)
# ---------------------------------------------------------------------------

def run_as_collect_step() -> None:
    """End-of-collect hook — wraps audit() + write; must never raise.

    Called from scripts/collect.py after the options accrual steps so the
    options entry coverage audit (audit_options_entry_coverage.py) can read the
    freshly updated options_accrual_audit.json for its consistency section.
    Idempotent; non-fatal.
    """
    import logging as _logging
    _log = _logging.getLogger("audit_options_accrual")
    try:
        report = audit()
        # Write observability artifact
        try:
            from datetime import datetime as _dt, timezone as _tz
            import json as _json
            from lib import config as _config
            out_dir = _config.data_dir() / "quality"
            out_dir.mkdir(parents=True, exist_ok=True)
            doc = {"generated_at": _dt.now(_tz.utc).isoformat(), **report}
            (out_dir / "options_accrual_audit.json").write_text(
                _json.dumps(doc, indent=2) + "\n"
            )
            _log.info("audit_options_accrual: wrote options_accrual_audit.json")
        except Exception as write_exc:  # noqa: BLE001
            _log.warning("audit_options_accrual: write failed (non-fatal): %s", write_exc)
        for w in report.get("warnings", []):
            _log.warning("audit_options_accrual: %s", w)
        for f in report.get("fail_reasons", []):
            _log.error("audit_options_accrual: %s", f)
    except Exception as exc:  # noqa: BLE001
        _log.error("[audit_options_accrual] collect step crashed (non-fatal): %s", exc)


if __name__ == "__main__":
    sys.exit(main())
