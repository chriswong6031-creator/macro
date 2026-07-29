"""scripts/build_flow_archive.py — dated tide/dte_tide archives for the live-flow poller.

WHY THIS EXISTS (OIP W0, T-lane). `live_flow/tide_current.json` and
`live_flow/dte_tide_current.json` are OVERWRITTEN every poller cycle, so at 16:05 ET the
session's story is gone: nothing can read back what the tide did today. This module adds a
second, DATE-KEYED copy of the very same bytes —

    live_flow/tide/{YYYY-MM-DD}.json          live_flow/tide/dates.json
    live_flow/dte_tide/{YYYY-MM-DD}.json      live_flow/dte_tide/dates.json

— so the day's FINAL write is the settled record the nightly Session Digest (OIP E1,
research/options_estate/OIP_MASTERPLAN.md §6 E1 / §7) reads at the close.

The payloads need no change: `engine/live_flow.build_tide_current` and
`build_dte_tide_current` already emit the FULL-SESSION cumulative series (every minute of
`market_tide_minutes` / `sector_tide` / `dte_tide` from the open, cumulated), not
instantaneous state — so the last write of the day is by construction the whole day. This
module therefore never touches the payloads or the current keys: it re-uses the local file
the poller already wrote and queues ONE extra R2 key for it. One write, two keys — the live
copy and the archived copy can never disagree byte-for-byte.

Ledger law (CLAUDE.md §Ledgers, OIP §0.9): this is a live intraday lane. It writes ZERO
`data/` artifacts — only the gitignored `data/live_flow_out/` staging dir (.gitignore:340)
and R2. Nothing here advances a forward ledger.

Idiom credit: this is the per-family twin of the per-root dated-surface layout in
`scripts/build_flow_surface.py` (`dated_surface_keys` / `merge_surface_dates` /
`prune_surface_dates`), and re-uses that module's `is_session_date` / `cadence_label`
helpers so the two families can never disagree on what a session date is. Differences:
  • the tide families are market-wide SINGLETONS (one file per session, not per root), so
    the index is keyed `family`, not `root`;
  • retention is 30 sessions, not 10 (§7: the digest ledger is the durable record, but the
    archives must outlive a long weekend plus a digest outage — surface archives stay 10);
  • `dates.json` is re-staged and queued EVERY cycle, so a missing or corrupt index heals in
    the SAME cycle — a `--once` / `--rth-only` run (the plist's own cold-start recipe) must
    never exit having deferred its heal to a cycle that will not run (#3499 / #F3-04).

Reader contract (for the digest lane): `dates.json` is a BEST-EFFORT index, not a warranty.
It never promises a session the retention prune has already deleted (the list is trimmed to
`retain`), but a listed session CAN still 404 — the local ledger records a date in the same
cycle that queues its upload, so a failed R2 PUT leaves the index one session ahead of the
store. Readers must tolerate a miss and print the gap rather than assume coverage.

Never a CI module — nothing here prints GitHub annotations (§0.15 n/a); it runs only inside
the launchd poller on the M1. Every public function is pure or fail-soft: a failure in this
lane must never cost the poller a cycle or blank a current key.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

# Shared vocabulary with the per-root surface archive — one definition of "session date"
# and one cadence-label table for both families.
from scripts.build_flow_surface import cadence_label, is_session_date

log = logging.getLogger(__name__)

# R2 prefix the poller publishes under (mirrors live_flow_poller.R2_PREFIX).
R2_LIVE_FLOW_PREFIX = "live_flow/"

# The archived families. CLOSED SET on purpose: a typo'd family would create an R2 prefix
# the retention prune does not recognize and would therefore never clean up (the same law
# `dated_surface_keys` enforces for malformed dates). `live_flow/events/` (OIP E1) is NOT a
# W0 writer — session events are derived nightly by the digest lane instead.
TIDE_FAMILY = "tide"
DTE_TIDE_FAMILY = "dte_tide"
ARCHIVE_FAMILIES = (TIDE_FAMILY, DTE_TIDE_FAMILY)

# Retention: newest N sessions per family (OIP §7 — retain >= 30). Config override
# live_flow.archive_retain_sessions. ~30 sessions x ~200 KB ≈ 6 MB per family.
ARCHIVE_RETAIN_SESSIONS = 30

# Public per-family sessions index (staged locally AND uploaded; doubles as the local
# ledger so the per-cycle write path needs no R2 read).
ARCHIVE_DATES_NAME = "dates.json"


# ── keys + staging paths ────────────────────────────────────────────────────────────

def _check_family(family: object) -> str:
    """Return the validated family name, or raise ValueError.

    Closed set — see ARCHIVE_FAMILIES. A junk family must never reach an R2 key.
    """
    if not isinstance(family, str) or family not in ARCHIVE_FAMILIES:
        raise ValueError(f"family {family!r} is not one of {ARCHIVE_FAMILIES}")
    return family


def family_prefix(family: str) -> str:
    """R2 prefix for a family: `live_flow/{family}/`.

    THE TRAILING SLASH IS LOAD-BEARING. `live_flow/tide` (no slash) also prefix-matches
    `live_flow/tide_current.json` — the object the live Terminal reads every 30s. Every
    list/delete in this module goes through here so a retention sweep can never see, let
    alone delete, a current key.
    """
    return f"{R2_LIVE_FLOW_PREFIX}{_check_family(family)}/"


def dated_archive_key(family: str, session_date: str) -> str:
    """R2 key for a family's dated archive: `live_flow/{family}/{YYYY-MM-DD}.json`.

    Raises ValueError on a malformed family or session_date, so a bad date can never create
    a junk key that the retention prune would then refuse to recognize (and never clean up)
    — the same guard as `build_flow_surface.dated_surface_keys`.

    FORMAT ONLY — deliberately NOT calendar-gated. The retention prune has to be able to
    rebuild a key for any date it finds in the store, including a junk/holiday object written
    by an older build, or it could never delete it. The trading-calendar gate belongs on the
    WRITE path (`is_market_session`, enforced in `stage_dated_archives`).
    """
    if not is_session_date(session_date):
        raise ValueError(f"session_date {session_date!r} is not YYYY-MM-DD")
    return f"{family_prefix(family)}{session_date}.json"


def is_market_session(session_date: object) -> bool:
    """True when `session_date` is a well-formed date AND a real NYSE trading session.

    `is_session_date` is only a FORMAT regex (build_flow_surface:564), and the poller's
    `_within_rth` only checks weekday + clock — neither knows about market holidays, and
    launchd fires on Thanksgiving and Good Friday just the same. An empty holiday payload
    archived under a dated key would become `dates.json`'s `latest`, poisoning the digest's
    session discovery and burning one of ~30 retention slots (~9 holidays/yr).

    FAILS CLOSED: if the calendar cannot be consulted we do not know whether today trades,
    so we skip the write and log loudly (once per cycle — deliberately hard to miss) rather
    than risk poisoning the store. `lib.nyse_calendar` is pure stdlib and already imported
    elsewhere in the poller, so this path is close to unreachable in practice.
    """
    if not is_session_date(session_date):
        return False
    try:
        from datetime import date

        from lib.nyse_calendar import is_session
        return bool(is_session(date.fromisoformat(str(session_date))))
    except Exception as e:  # noqa: BLE001 — fail closed, loudly
        log.warning("archive: NYSE calendar unavailable for %s (%s) — archive write SKIPPED",
                    session_date, e)
        return False


def dates_index_key(family: str) -> str:
    """R2 key for a family's sessions index: `live_flow/{family}/dates.json`."""
    return f"{family_prefix(family)}{ARCHIVE_DATES_NAME}"


def archive_out_dir(family: str) -> Path:
    """`data/live_flow_out/{family}/` (gitignored staging; created on demand).

    Holds only this lane's own staged file — `dates.json`, whose staged path mirrors its R2
    key suffix (`{family}/dates.json`). The dated PAYLOAD is never re-staged here: it is the
    poller's existing `live_flow_out/{tide,dte_tide}_current.json` file uploaded under a
    second key, so no staged path corresponds to `{family}/{DATE}.json`.
    """
    from lib import config  # local import — keeps the pure helpers importable without config

    p = config.data_dir() / "live_flow_out" / _check_family(family)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_json_atomic(path: Path, obj: dict) -> Path:
    """Atomic JSON write (tmp + rename), mirroring live_flow_poller._write_json."""
    tmp = path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(obj, default=str))
    tmp.rename(path)
    return path


# ── sessions index (dates.json) ─────────────────────────────────────────────────────

def _retain_or_default(retain: object) -> int:
    """Coerce a retention count to a SAFE positive int, falling back loudly to the default.

    A misconfigured `live_flow.archive_retain_sessions` of 0 or -1 must never reach the
    prune: `dates[keep_n:]` with keep_n <= 0 selects EVERY dated object — including today's
    — so a stray minus sign would erase the whole archive on the next sweep. Non-numeric or
    non-positive values are refused with a warning and the module default is used instead.
    """
    try:
        n = int(retain)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        log.warning("archive: retain=%r is not a positive session count — using %d",
                    retain, ARCHIVE_RETAIN_SESSIONS)
        return ARCHIVE_RETAIN_SESSIONS
    return n


def build_archive_dates_index(family: str, dates, *, cadence_sec: int, asof: str,
                              retain: int = ARCHIVE_RETAIN_SESSIONS,
                              source: str = "poller") -> dict:
    """Build a family's sessions index — retained sessions NEWEST FIRST.

    The digest lane reads this to discover which sessions it can settle; `latest` is
    dates[0] (null when empty). Non-date entries are dropped and duplicates collapsed, so a
    corrupt ledger can never publish a bogus session, and the list is trimmed to `retain` —
    dates.json never promises a session the retention prune has already deleted.

    Cadence is carried verbatim from the true write interval (the honesty law shared with
    build_flow_surface.build_index): the index never claims a cadence the poller lacks.
    """
    keep_n = _retain_or_default(retain)
    clean = sorted({d for d in (dates or []) if is_session_date(d)}, reverse=True)
    clean = clean[:keep_n]
    return {
        "schema":     "live_flow.archive_dates/v1",
        "family":     _check_family(family),
        "dates":      clean,
        "latest":     clean[0] if clean else None,
        "count":      len(clean),
        "retain":     keep_n,
        "cadenceSec": int(cadence_sec),
        "cadence":    cadence_label(cadence_sec),
        "asof":       asof,
        "source":     source,
    }


def is_archive_dates(x: object) -> bool:
    """Validator for a family's dates.json.

    Contract: `dates` is a list of YYYY-MM-DD strings sorted NEWEST FIRST, `latest` is
    dates[0] (null when empty), `family` is a known family, and cadenceSec is an honest int.
    The digest lane checks the same things before trusting a session list.
    """
    if not isinstance(x, dict):
        return False
    dates = x.get("dates")
    if not isinstance(dates, list) or not all(is_session_date(d) for d in dates):
        return False
    if dates != sorted(dates, reverse=True):
        return False
    latest = x.get("latest")
    if dates:
        if latest != dates[0]:
            return False
    elif latest is not None:
        return False
    return (
        isinstance(x.get("cadenceSec"), int)
        and not isinstance(x.get("cadenceSec"), bool)
        and x.get("family") in ARCHIVE_FAMILIES
    )


def load_dates_ledger(family: str) -> list[str]:
    """Session dates this poller has recorded locally for a family (newest first); [] if none.

    The public dates.json doubles as the ledger, so the per-cycle write path needs no R2
    read. A wiped staging dir (host redeploy) or a corrupt file simply restarts the ledger:
    the same cycle re-writes it, and the once-per-session prune merges R2 truth back in.
    """
    try:
        f = archive_out_dir(family) / ARCHIVE_DATES_NAME
        if f.exists():
            doc = json.loads(f.read_text())
            return [d for d in (doc.get("dates") or []) if is_session_date(d)]
    except Exception as e:  # noqa: BLE001 — a corrupt ledger heals, it never raises
        log.debug("archive: dates ledger load failed for %s: %s", family, e)
    return []


def stage_dates_index(family: str, dates, *, cadence_sec: int, asof: str,
                      retain: int = ARCHIVE_RETAIN_SESSIONS) -> Path:
    """Write a family's public dates.json from `dates`; return its local path."""
    doc = build_archive_dates_index(family, dates, cadence_sec=cadence_sec, asof=asof,
                                    retain=retain)
    return _write_json_atomic(archive_out_dir(family) / ARCHIVE_DATES_NAME, doc)


def merge_archive_dates(family: str, dates, *, cadence_sec: int, asof: str,
                        retain: int = ARCHIVE_RETAIN_SESSIONS) -> list[str]:
    """Union `dates` into the local ledger, rewrite dates.json, return the retained list.

    Used two ways: the per-cycle write path merges in today's session date (so a missing or
    malformed index is rebuilt and re-uploaded THIS cycle — heal-now, never deferred), and
    the once-per-session retention prune merges back R2 truth (self-healing after a staging
    wipe). Never raises — a ledger failure must not cost the caller its archive upload; on
    failure the previously-recorded list is returned unchanged.
    """
    try:
        merged = set(load_dates_ledger(family)) | {d for d in (dates or []) if is_session_date(d)}
        stage_dates_index(family, merged, cadence_sec=cadence_sec, asof=asof, retain=retain)
        return sorted(merged, reverse=True)[: _retain_or_default(retain)]
    except Exception as e:  # noqa: BLE001
        log.warning("archive: dates ledger merge failed for %s: %s", family, e)
        return load_dates_ledger(family)


# ── per-cycle staging (the poller's entry point) ────────────────────────────────────

def stage_dated_archives(
    *,
    paths_by_family: dict,
    session_date: str,
    asof: str,
    cadence_sec: int,
    retain_sessions: int = ARCHIVE_RETAIN_SESSIONS,
) -> list[tuple[Path, str]]:
    """Queue the dated copy + sessions index for each family; return [(local_path, r2_key), …].

    Called from the live_flow poller loop right after `tide_current.json` /
    `dte_tide_current.json` are written, with those very paths:

        {TIDE_FAMILY: tide_path, DTE_TIDE_FAMILY: dte_tide_path}

    For each known family with an existing local file it returns
      1. (that same file, `live_flow/{family}/{DATE}.json`)  — one write, two keys, so the
         current key and the archive can never diverge; the day's LAST cycle leaves the
         settled record, and re-running a cycle just overwrites the same key (idempotent);
      2. (dates.json, `live_flow/{family}/dates.json`) — re-staged every cycle, so the index
         heals in-cycle.

    Returns [] — writing NOTHING — unless `session_date` is a real NYSE trading session
    (`is_market_session`): launchd fires on market holidays too, and an empty holiday payload
    would become `dates.json`'s `latest` and poison the digest's session discovery.

    Fenced PER FAMILY: a failure for one family (bad date, unwritable staging dir) is logged
    and skipped, never raised, and never costs the other family its keys. The caller's
    current-key writes and uploads are entirely independent of this function — they are
    already on disk before it runs and are uploaded unconditionally afterwards regardless of
    what (or whether) it returns — so nothing here can blank or delay them.
    """
    out: list[tuple[Path, str]] = []
    paths_by_family = paths_by_family or {}
    if not is_market_session(session_date):
        # Not a trading session (holiday, malformed date, or calendar unavailable) — the
        # current keys still publish; only the dated archive is withheld.
        log.info("archive: %s is not an NYSE trading session — no dated archive staged",
                 session_date)
        return out
    for family in ARCHIVE_FAMILIES:            # deterministic order, closed set
        local = paths_by_family.get(family)
        if local is None:
            continue
        try:
            local = Path(local)
            if not local.exists():
                # Queueing a missing file would log an upload warning every cycle.
                log.warning("archive: %s payload %s missing — dated copy skipped",
                            family, local)
                continue
            out.append((local, dated_archive_key(family, session_date)))
            merge_archive_dates(family, [session_date], cadence_sec=cadence_sec,
                                asof=asof, retain=retain_sessions)
            # merge_archive_dates is fail-soft: only queue the index when it is really on
            # disk, so a degraded ledger doesn't warn once a cycle for a path never written.
            dates_local = archive_out_dir(family) / ARCHIVE_DATES_NAME
            if dates_local.exists():
                out.append((dates_local, dates_index_key(family)))
        except Exception as e:  # noqa: BLE001 — the other family must still be queued
            log.warning("archive: dated staging failed for %s: %s", family, e)
    return out


# ── retention (once per session) ────────────────────────────────────────────────────

def _list_session_dates(s3, bucket: str, family: str) -> tuple[bool, list[str]]:
    """(listing_ok, session dates newest-first). Distinguishes EMPTY from FAILED.

    An empty store and a failed listing both look like `[]`, but they must not be treated
    alike: empty is a normal first-session state (nothing to prune, sweep is done), while a
    failure means retention is unverified. Only the failure sets ok=False.
    """
    out: list[str] = []
    try:
        prefix = family_prefix(family)
        tok = None
        while True:
            kw: dict = {"Bucket": bucket, "Prefix": prefix, "Delimiter": "/"}
            if tok:
                kw["ContinuationToken"] = tok
            r = s3.list_objects_v2(**kw) or {}
            for o in r.get("Contents", []) or []:
                name = (o.get("Key") or "")[len(prefix):]
                if name.endswith(".json") and is_session_date(name[: -len(".json")]):
                    out.append(name[: -len(".json")])
            if not r.get("IsTruncated"):
                break
            tok = r.get("NextContinuationToken")
            if not tok:
                # Truncated with no continuation token: re-issuing the same request would
                # repeat this page forever, and a hang inside the per-minute poller loop is
                # not something an `except` can rescue. Stop and report the listing as
                # incomplete so retention is not believed-enforced on a partial page.
                log.warning("archive: %s listing truncated with no continuation token — "
                            "treating as incomplete", family)
                return False, sorted(set(out), reverse=True)
    except Exception as e:  # noqa: BLE001
        log.warning("archive: list session dates failed for %s: %s", family, e)
        return False, []
    return True, sorted(set(out), reverse=True)


def list_archive_session_dates(s3, bucket: str, family: str) -> list[str]:
    """Session dates present in R2 for a family, newest first. [] on any failure.

    One cheap listing per family per session (~30 small objects). Only `{YYYY-MM-DD}.json`
    object names count — `dates.json` is not a session and is never returned, so it can
    never be selected for deletion. Callers that must tell empty from failed use
    `_list_session_dates`.
    """
    return _list_session_dates(s3, bucket, family)[1]


def prune_archive_dates(s3, bucket: str, family: str,
                        *, keep: int = ARCHIVE_RETAIN_SESSIONS) -> dict:
    """Delete a family's dated objects older than the newest `keep` sessions.

    Returns {ok, retained, deleted_dates, deleted_objects}. NEVER raises. Every deletion
    target is REBUILT from `dated_archive_key`, so this can only ever delete a key this
    module itself would write — never `dates.json`, and never a current key such as
    `live_flow/tide_current.json` (see `family_prefix` on the trailing slash).

    `ok` is the honest "retention is enforced as of now" flag:
      • empty store           → ok=True  (nothing to prune is a success, not a failure)
      • listing failed        → ok=False
      • any per-key delete error (R2 reports these in the response's `Errors` array, NOT as
        an exception) → ok=False, and those keys are excluded from the deleted counts
    The caller treats ok=False as "retry NEXT SESSION" — never as a per-cycle retry, which
    would re-issue this listing ~200×/session while the failure persists.
    """
    res: dict = {"ok": False, "retained": [], "deleted_dates": [], "deleted_objects": 0}
    try:
        keep_n = _retain_or_default(keep)
        listed_ok, dates = _list_session_dates(s3, bucket, family)
        if not listed_ok:
            return res                      # already logged; retention unverified
        if not dates:
            res["ok"] = True                # empty store — nothing to prune
            return res
        res["retained"] = dates[:keep_n]
        stale = dates[keep_n:]
        deletes_ok = True
        if stale:
            keys = [dated_archive_key(family, d) for d in stale]
            failed: set[str] = set()
            for i in range(0, len(keys), 1000):   # S3/R2 delete_objects caps at 1000
                batch = keys[i:i + 1000]
                resp = s3.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": k} for k in batch]}) or {}
                # A per-key failure is reported in the response body, not raised. Counting
                # the batch length regardless would fabricate the deleted count and leave
                # retention BELIEVED-enforced while objects survive.
                errors = resp.get("Errors") or []
                if errors:
                    deletes_ok = False
                    failed.update(str(e.get("Key")) for e in errors)
                    for e in errors[:5]:
                        log.warning("archive: delete refused for %s: %s %s",
                                    e.get("Key"), e.get("Code"), e.get("Message"))
                res["deleted_objects"] += len(batch) - len([k for k in batch if k in failed])
            res["deleted_dates"] = [d for d in stale
                                    if dated_archive_key(family, d) not in failed]
            log.info("archive: pruned %d/%d stale session(s) for %s (%d objects); retained %s",
                     len(res["deleted_dates"]), len(stale), family,
                     res["deleted_objects"], res["retained"])
        res["ok"] = deletes_ok
    except Exception as e:  # noqa: BLE001
        log.warning("archive: retention prune failed for %s: %s", family, e)
    return res
