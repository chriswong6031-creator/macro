"""scripts/build_session_digest.py — OIP E1 nightly session-digest builder (data only).

WHAT: after the close, reads the intraday options plane's archived per-minute stamps back
out of R2 and writes one settled session record per root — the Terminal→EOD bridge.  Zero
UI: this builder renders no page and touches no template.

INPUTS (all read-only, all absent-safe):
  R2 live_flow/surface/{ROOT}/dates.json      which sessions the poller archived
  R2 live_flow/surface/{ROOT}/{DATE}/idx.json the session's stamp list + true cadence
  R2 live_flow/surface/{ROOT}/{DATE}/{HHMM}.json
                                              per-stamp replay frames (netprem grid, spot,
                                              and — once the greek tap is armed — walls)
  R2 live_flow/tide/{DATE}.json               MARKET-WIDE signed tape archive (a sibling
  R2 live_flow/dte_tide/{DATE}.json           lane is adding these; absent today)
  site/options_structure/gex_state/{ROOT}.json   EOD flip + wall levels, vintage printed
  data/options_session/ledger.parquet         prior sessions (yesterday's close walls become
                                              today's open walls when the greek tap is dark)

NEVER READ: Supabase, `public.alerts`, or any user-scoped row.  Those are owner-scoped user
data under RLS; the digest is a system-data artifact and reading a user's alerts to describe
a market session would be a privacy breach for no product gain.

OUTPUTS:
  data/options_session/{DATE}/{ROOT}.json     the settled record (schema options_session.v1)
  site/session/{ROOT}.json                    the latest session, for future surfaces
  data/options_session/ledger.parquet         one row per (date, root) — NIGHTLY LANE ONLY

LANE LAW: every `data/` write — the dated records AND the forward-ledger append — is gated on
`engine.ledger_lane.nightly_advance_enabled()` (COLLECT_LANE=nightly, the shared helper, not a
local copy).  An off-lane run (replay, intraday probe, fastpath) refreshes only the `site/`
latest pointer, which is a display artifact nobody grades.  Ledger dedup on (date, root) keeps
the FIRST row, so a replay can add sessions but never rewrites one already on the record.

CLOCK LABELS ARE NOT TRUSTED: `engine/live_flow._minute_key` localizes naive exchange
timestamps as UTC before converting to ET, so the tide/dte minute labels run a whole timezone
offset early (a 09:30–16:00 session labelled 05:30–11:59).  Every label the digest emits goes
through `session_digest.clock_offset_minutes`, which corrects a whole-hour skew when the first
label precedes the session open and is a no-op otherwise — so it fixes the defect, preserves a
genuinely late poller start, and disarms itself once `_minute_key` is repaired.  Fixing
`_minute_key` is out of this builder's scope (it changes live payload bytes and the Terminal's
axis) and is filed separately.

PLACEMENT: serial step in daily.yml's `engine` job immediately after OEU M-CMD.  It must sit
AFTER the parallel band's barrier because it reads site/options_structure/gex_state/*.json,
which build_gex_board writes inside the cl_gex cluster — the same cross-phase-dependency
reasoning that puts build_options_command there.  The engine job also carries
COLLECT_LANE=nightly at job level and its "commit engine outputs" step already stages both
`data/` and `site/`, so no new commit path is introduced.

R2 READ PATTERN: the self-contained `_r2_client()` convention (scripts/build_flow_enrich.py,
scripts/mirror_terminal_context_r2.py, scripts/live_flow_poller.py), not
`scripts/publish_r2._client`.  Reasons: this builder does small GETs under the same
`live_flow/` prefix build_flow_enrich already reads, it needs none of publish_r2's
manifest/ETag/dir-mapping machinery, and publish_r2's client is tuned for 60 GB bulk syncs
(64-connection pool, 10 adaptive retries) which is the wrong failure profile for a handful
of small keys inside a 200-minute nightly job.

FAIL-SOFT: always exits 0.  Every absent or stale input degrades to a printed null with a
plain-word note; nothing is fabricated and no traceback escapes.  Annotations are emitted
with a bare `print(..., flush=True)` so `::warning` starts its line (a logger prefix makes
GitHub drop the annotation silently — tests/test_gh_annotation_line_start.py).

RUN:
  python -m scripts.build_session_digest                      # last completed session
  python -m scripts.build_session_digest --date 2026-07-28
  python -m scripts.build_session_digest --roots SPY,QQQ --dry-run
  python -m scripts.build_session_digest --from-dir /path/to/surface   # offline replay
  python -m scripts.build_session_digest --selftest
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time as _time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import session_digest as sd                     # noqa: E402
from engine.ledger_lane import nightly_advance_enabled      # noqa: E402
from lib import config, nyse_calendar                       # noqa: E402

log = logging.getLogger("build_session_digest")

# R2 prefixes — must match the writers verbatim (scripts/build_flow_surface.R2_SURFACE_PREFIX
# and scripts/live_flow_poller.R2_PREFIX).
R2_SURFACE_PREFIX = "live_flow/surface/"
R2_TIDE_PREFIX = "live_flow/tide/"
R2_DTE_TIDE_PREFIX = "live_flow/dte_tide/"

# Roots to try when nothing narrows the list.  Mirrors
# scripts/build_flow_surface.DEFAULT_SURFACE_ROOTS; config live_flow.surface_roots wins.
DEFAULT_ROOTS = ["SPY", "QQQ", "IWM"]

# Parallel GETs for the per-stamp spot scan.  A session is ~78 stamps at 5-minute cadence,
# and the per-stamp spot lives ONLY inside each stamp's own frame (build_flow_surface's
# frame_for_stamp drops spot_path), so the scan is one small GET per stamp.  8 keeps the
# wall clock in single-digit seconds without becoming a burst against R2.
SPOT_SCAN_WORKERS = 8

# Bounded walk-back when the newest stamp's frame will not load: the full-day arc lives in
# the LAST frame (each stamp file is the day truncated to that stamp), so a corrupt tail
# would otherwise cost the whole session.  3 attempts, then the root degrades honestly.
FRAME_FALLBACK_TRIES = 3

LEDGER_REL = "options_session/ledger.parquet"


# ── annotations (bare print — never through the logger) ───────────────────────────

def _warn(title: str, msg: str) -> None:
    """Emit a GitHub annotation that STARTS its line, plus a normal log line.

    A logger's format prefixes the message ("WARNING ::warning ..."), and GitHub then drops
    the annotation without a word — the alarm reviews as present and produces nothing.
    """
    print(f"::warning title={title}::{msg}", flush=True)
    log.warning("%s: %s", title, msg)


# ── R2 ───────────────────────────────────────────────────────────────────────────

def _r2_client():
    """boto3 S3 client for R2, or None when creds are absent (graceful degrade)."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3
        from botocore.config import Config

        kw = dict(region_name="auto", signature_version="s3v4",
                  max_pool_connections=max(16, SPOT_SCAN_WORKERS * 2),
                  retries={"max_attempts": 3, "mode": "standard"},
                  connect_timeout=15, read_timeout=30)
        try:
            cfg = Config(**kw, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                            aws_secret_access_key=sk, config=cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("session_digest: R2 client build failed: %s", e)
        return None


class ArchiveReader:
    """Reads the surface/tide archives from R2, or from a local directory for replay.

    `from_dir` is treated as a mirror of the BUCKET ROOT, so every key resolves the same way
    it does on R2 — `<dir>/live_flow/surface/{ROOT}/{DATE}/idx.json`,
    `<dir>/live_flow/tide/{DATE}.json`.  One key shape for both sources means a replay
    exercises the real path rather than a parallel one that can drift.  Counts every read so
    the builder can report exactly how many objects a night costs.
    """

    def __init__(self, *, s3=None, bucket: str | None = None, from_dir: Path | None = None):
        self.s3 = s3
        self.bucket = bucket
        self.from_dir = Path(from_dir) if from_dir else None
        self.gets = 0
        self.misses = 0

    @property
    def live(self) -> bool:
        return bool(self.from_dir) or bool(self.s3 and self.bucket)

    def get_json(self, key: str) -> dict | None:
        """Fetch and parse one JSON object; None on absence or any parse/transport error."""
        self.gets += 1
        if self.from_dir is not None:
            p = self.from_dir / key
            try:
                return json.loads(p.read_text())
            except Exception:  # noqa: BLE001 — absence and corruption are the same answer
                self.misses += 1
                return None
        if not (self.s3 and self.bucket):
            self.misses += 1
            return None
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            return json.loads(resp["Body"].read())
        except Exception as e:  # noqa: BLE001
            self.misses += 1
            log.debug("session_digest: get %s failed: %s", key, e)
            return None

    # ── keyed helpers (key shapes mirror the writers) ────────────────────────────
    def dates_index(self, root: str) -> dict | None:
        return self.get_json(f"{R2_SURFACE_PREFIX}{root.upper()}/dates.json")

    def session_index(self, root: str, session_date: str) -> dict | None:
        return self.get_json(f"{R2_SURFACE_PREFIX}{root.upper()}/{session_date}/idx.json")

    def stamp_frame(self, root: str, session_date: str, stamp: str) -> dict | None:
        return self.get_json(
            f"{R2_SURFACE_PREFIX}{root.upper()}/{session_date}/{stamp}.json")

    def tide(self, session_date: str) -> dict | None:
        return self.get_json(f"{R2_TIDE_PREFIX}{session_date}.json")

    def dte_tide(self, session_date: str) -> dict | None:
        return self.get_json(f"{R2_DTE_TIDE_PREFIX}{session_date}.json")


# ── local store reads ────────────────────────────────────────────────────────────

def read_levels(site: Path, root: str) -> dict | None:
    """EOD flip/wall map for a root from the gex_state payload, with its vintage.

    `asof` is an ISO timestamp; its DATE is the vintage a surface must print beside any
    level.  A payload that will not parse yields None rather than a partial map.
    """
    p = site / "options_structure" / "gex_state" / f"{root.upper()}.json"
    try:
        doc = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(doc, dict):
        return None
    return {
        "flip": doc.get("gamma_flip"),
        "call_wall": doc.get("call_wall"),
        "put_wall": doc.get("put_wall"),
        "spot": doc.get("spot"),
        "vintage": str(doc.get("asof") or "")[:10] or None,
        "source": f"site/options_structure/gex_state/{root.upper()}.json",
    }


def prior_close_walls(data: Path, root: str, session_date: str) -> tuple[dict | None, str | None]:
    """Yesterday's close walls from the ledger — today's open walls when greeks are dark.

    Session-filtered through `lib.nyse_calendar`: the newest ledger row STRICTLY BEFORE this
    session on a real NYSE session date.  Reading `.iloc[-1]` off a date-sorted store is the
    #3721 weekend-row defect; here it would silently hand a Saturday row to a Monday digest.
    """
    p = data / LEDGER_REL
    if not p.exists():
        return None, None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.debug("session_digest: ledger read failed: %s", e)
        return None, None
    if df is None or df.empty or "date" not in df.columns:
        return None, None
    try:
        want = sd.as_session_date(session_date)
        sub = df[df["root"].astype(str).str.upper() == root.upper()].copy()
        if sub.empty:
            return None, None
        sub["_d"] = pd.to_datetime(sub["date"], errors="coerce").dt.date
        sub = sub[sub["_d"].notna()]
        sub = sub[[d < want and nyse_calendar.is_session(d) for d in sub["_d"]]]
        if sub.empty:
            return None, None
        sub = sub.sort_values("_d")
        row = sub.iloc[-1]
        call, put = row.get("wall_call_close"), row.get("wall_put_close")
        if call is None and put is None:
            return None, None
        walls = {"call": sd.as_float(call), "put": sd.as_float(put)}
        if walls["call"] is None and walls["put"] is None:
            return None, None
        return walls, f"prior session record ({row['_d'].isoformat()})"
    except Exception as e:  # noqa: BLE001
        log.debug("session_digest: prior-wall lookup failed: %s", e)
        return None, None


# ── per-root digest ──────────────────────────────────────────────────────────────

def discover_roots(reader: ArchiveReader, candidates: list[str],
                   session_date: str) -> tuple[list[str], set[str]]:
    """(roots to try, roots whose dates.json PROMISED this session).

    A root with no dates.json is still tried — the session index is the real authority and it
    costs one small GET.  A root with a healthy dates.json that does not list this session is
    skipped.  The promised set is returned so a promised-but-absent session can be annotated
    instead of silently skipped: the dated indexes are best-effort, and "listed but missing"
    and "never traded" must not look the same from outside.
    """
    out: list[str] = []
    promised: set[str] = set()
    for r in candidates:
        doc = reader.dates_index(r)
        if isinstance(doc, dict):
            dates = doc.get("dates")
            if isinstance(dates, list) and session_date in [str(d) for d in dates]:
                promised.add(r)
                out.append(r)
                continue
            if isinstance(dates, list) and dates:
                continue          # index is healthy and this session is not in it
        out.append(r)
    return out, promised


def scan_session(
    reader: ArchiveReader,
    *,
    root: str,
    session_date: str,
    stamps: list[str],
    workers: int,
    spot_scan: bool,
) -> tuple[dict | None, str | None, dict[str, float | None], dict | None, list[str] | None]:
    """One pass over the archived stamps → (frame, its stamp, spots, open walls, stamps read).

    Two facts force a per-stamp read: `frame_for_stamp` (scripts/build_flow_surface.py)
    writes each stamp's scalar `spot` but DROPS `spot_path`, and it emits that stamp's own
    `walls` rather than the whole `walls_path` — so the price path and the opening wall map
    exist only spread across the per-stamp files.  The day's ARC needs just one file: every
    stamp file is the session truncated to that stamp, so the newest is the full day.

    With `spot_scan` off, only the tail window plus the first stamp are fetched (4 GETs);
    level-crossing events are then simply absent, and the record says so.  A stamp that will
    not load maps to None — a gap in the tape stays a gap.

    The fifth return value is the list of stamps whose object actually came back, or None when
    the scan was skipped (nothing was verified, so nothing may be claimed).  The dated indexes
    are best-effort — a stamp can be listed while its PUT failed — and coverage must count what
    was read, not what was promised.
    """
    tail = stamps[-FRAME_FALLBACK_TRIES:] if stamps else []
    wanted = list(stamps) if spot_scan else sorted(set(tail) | ({stamps[0]} if stamps else set()))

    def one(stamp: str) -> tuple[str, dict | None]:
        return stamp, reader.stamp_frame(root, session_date, stamp)

    frames: dict[str, dict | None] = {}
    if wanted:
        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
            for stamp, fr in ex.map(one, wanted):
                frames[stamp] = fr if isinstance(fr, dict) else None

    # Full-day frame: newest readable stamp, walking back at most FRAME_FALLBACK_TRIES so a
    # single corrupt tail object cannot cost the whole session.
    frame, frame_stamp = None, None
    for stamp in reversed(tail):
        fr = frames.get(stamp)
        if isinstance(fr, dict) and fr.get("grids"):
            frame, frame_stamp = fr, stamp
            break

    spots: dict[str, float | None] = {}
    read: list[str] | None = None
    if spot_scan:
        spots = {s: sd.as_float((frames.get(s) or {}).get("spot")) for s in stamps}
        read = [s for s in stamps if isinstance(frames.get(s), dict)]

    open_frame = frames.get(stamps[0]) if stamps else None
    open_walls = (open_frame or {}).get("walls")
    return frame, frame_stamp, spots, open_walls, read


def digest_root(
    reader: ArchiveReader,
    *,
    root: str,
    session_date: str,
    site: Path,
    data: Path,
    tide_doc: dict | None,
    dte_doc: dict | None,
    scan_spots: bool = True,
    workers: int = SPOT_SCAN_WORKERS,
    listed: bool = False,
) -> dict | None:
    """The `options_session.v1` record for one root, or None when the archive has no session."""
    root = root.upper()
    idx = reader.session_index(root, session_date)
    if not isinstance(idx, dict):
        if listed:
            # dates.json promised this session and the index object is not there.  Best-effort
            # indexes make that possible (a failed PUT), and it is worth an annotation: a
            # silently skipped root is indistinguishable from a root that never traded.
            _warn("session_digest",
                  f"{root} {session_date}: the archive's session list promises this session "
                  "but its index object is absent — no record for this root")
        return None
    stamps = [str(s) for s in (idx.get("stamps") or []) if str(s)]
    cadence = idx.get("cadenceSec")
    try:
        cadence = int(cadence)
    except (TypeError, ValueError):
        cadence = 0
    idx_date = str(idx.get("date") or "")[:10]
    if idx_date and idx_date != str(session_date)[:10]:
        _warn("session_digest",
              f"{root} {session_date}: archived index reports session {idx_date} — skipped "
              "rather than digested under the wrong date")
        return None

    frame, frame_stamp, spots, first_walls, read_stamps = scan_session(
        reader, root=root, session_date=session_date, stamps=stamps,
        workers=workers, spot_scan=bool(scan_spots))
    if frame is None:
        _warn("session_digest",
              f"{root} {session_date}: no readable stamp frame ({len(stamps)} stamp(s) "
              "promised by the index) — record written with an empty arc")
    if read_stamps is not None and len(read_stamps) < len(stamps):
        # The dated indexes are best-effort: a listed stamp whose PUT failed is a hole, and it
        # is named here rather than absorbed into a coverage ratio nobody can decompose.
        _warn("session_digest",
              f"{root} {session_date}: {len(stamps) - len(read_stamps)} of {len(stamps)} "
              "minute stamps listed by the archive index could not be read back — coverage "
              "counts only the stamps that returned")

    # Intraday walls ride the frame only once the greek tap is armed (Lane G); until then no
    # stamp file carries `walls`, and the open falls back to the prior session's record.
    close_walls = frame.get("walls") if isinstance(frame, dict) else None

    levels = read_levels(site, root)
    open_source = None
    if not sd.walls_from_frame(first_walls):
        prior, src = prior_close_walls(data, root, session_date)
        if prior:
            first_walls = {"callWall": prior.get("call"), "putWall": prior.get("put")}
            open_source = src

    record = sd.build_session_record(
        root=root,
        session_date=session_date,
        asof=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        frame=frame,
        stamps=stamps,
        cadence_sec=cadence,
        spots_by_stamp=spots,
        read_stamps=read_stamps,
        open_frame_walls=first_walls,
        close_frame_walls=close_walls,
        levels=levels,
        dte_doc=dte_doc,
        tide_doc=tide_doc,
        inputs={
            "surface_index": bool(idx),
            "surface_stamps": len(stamps),
            "surface_frame_stamp": frame_stamp,
            "surface_stamps_read": len(read_stamps) if read_stamps is not None else None,
            "spot_scan": bool(spots),
            "levels_source": (levels or {}).get("source"),
            "levels_vintage": (levels or {}).get("vintage"),
            "tide_archive": bool(tide_doc),
            "dte_tide_archive": bool(dte_doc),
            "cadence_sec": cadence,
        },
    )
    if open_source:
        record["walls"]["open"]["source"] = open_source
    return record


# ── writes ───────────────────────────────────────────────────────────────────────

def _write_json_atomic(path: Path, obj: dict) -> Path:
    """Atomic JSON write (tmp + replace) — a killed run never leaves a truncated record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def write_latest(site: Path, record: dict) -> Path | None:
    """Write `site/session/{ROOT}.json` unless it already holds a NEWER session.

    "Latest" must only ever move forward: replaying an older date to backfill the ledger
    must not roll a live surface back to that older day.
    """
    p = site / "session" / f"{record['root']}.json"
    try:
        if p.exists():
            cur = json.loads(p.read_text())
            if isinstance(cur, dict):
                have = str(cur.get("session_date") or "")[:10]
                if have and have > str(record["session_date"])[:10]:
                    log.info("session_digest: %s latest keeps %s (newer than %s)",
                             record["root"], have, record["session_date"])
                    return None
    except Exception as e:  # noqa: BLE001
        log.debug("session_digest: latest read failed for %s: %s", record["root"], e)
    return _write_json_atomic(p, record)


def append_ledger(data: Path, rows: list[dict]) -> int:
    """Append rows to `data/options_session/ledger.parquet`.  LANE-GATED, keep-first.

    Gate: `engine.ledger_lane.nightly_advance_enabled()` (COLLECT_LANE=nightly) — the shared
    helper, not a local re-implementation.  Nightly is the sole advancer of forward ledgers;
    an off-lane append would displace the nightly row permanently.  Dedup keeps the FIRST
    row per (date, root), so a re-run can add sessions but never rewrite one.

    Returns the row count now in the store, or -1 when the lane is closed / the write failed.
    """
    if not nightly_advance_enabled():
        log.info("session_digest: ledger write skipped (COLLECT_LANE != nightly)")
        return -1
    if not rows:
        return -1
    path = data / LEDGER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd
        new_df = pd.DataFrame(rows, columns=sd.LEDGER_COLUMNS)
        new_df["date"] = pd.to_datetime(new_df["date"]).dt.strftime("%Y-%m-%d")
        if path.exists():
            old_df = pd.read_parquet(path)
            if "date" in old_df.columns:
                old_df["date"] = pd.to_datetime(old_df["date"]).dt.strftime("%Y-%m-%d")
            combined = pd.concat([old_df, new_df], ignore_index=True)
        else:
            combined = new_df
        combined = combined.drop_duplicates(subset=["date", "root"], keep="first")
        combined = combined.sort_values(["date", "root"]).reset_index(drop=True)
        combined.to_parquet(path, index=False)
        log.info("session_digest: ledger updated (%d rows)", len(combined))
        return len(combined)
    except Exception as e:  # noqa: BLE001
        _warn("session_digest", f"ledger write failed: {e}")
        return -1


# ── main ─────────────────────────────────────────────────────────────────────────

def default_session_date(now: datetime | None = None) -> str:
    """The last completed NYSE session, exchange-calendar-derived.

    `expected_last_session` already handles the run-before-midnight-ET case the rest of the
    repo's freshness checks use, so the nightly and a 02:00 ET re-run agree on the date.
    """
    return nyse_calendar.expected_last_session(now).isoformat()


def configured_roots() -> list[str]:
    """Surface roots from config `live_flow.surface_roots`, else the writer's defaults."""
    try:
        cfg = config.load() or {}
        roots = ((cfg.get("live_flow") or {}).get("surface_roots")) or []
        out = [str(r).upper() for r in roots if str(r).strip()]
        if out:
            return out
    except Exception as e:  # noqa: BLE001
        log.debug("session_digest: config roots unavailable: %s", e)
    return list(DEFAULT_ROOTS)


def run(
    *,
    session_date: str | None = None,
    roots: list[str] | None = None,
    from_dir: Path | None = None,
    dry_run: bool = False,
    scan_spots: bool = True,
    workers: int = SPOT_SCAN_WORKERS,
    root_dir: Path | None = None,
) -> dict:
    """Digest one session for every covered root.  Returns a run summary; never raises."""
    t0 = _time.monotonic()
    repo = Path(root_dir) if root_dir else config.ROOT
    cfg = config.load()["storage"]
    site = repo / cfg["site_dir"]
    data = repo / cfg["data_dir"]

    sess = str(session_date or default_session_date())
    try:
        d = sd.as_session_date(sess)
    except Exception:  # noqa: BLE001
        _warn("session_digest", f"unparseable --date {sess!r} — nothing digested")
        return {"ok": False, "session_date": sess, "roots": [], "reason": "bad_date"}
    if not nyse_calendar.is_session(d):
        _warn("session_digest",
              f"{sess} is not an NYSE session — nothing digested (weekend/holiday guard)")
        return {"ok": True, "session_date": sess, "roots": [], "reason": "not_a_session"}

    reader = ArchiveReader(s3=_r2_client() if from_dir is None else None,
                           bucket=os.environ.get("R2_BUCKET"),
                           from_dir=from_dir)
    if not reader.live:
        _warn("session_digest",
              "no archive source available (R2_ENDPOINT/R2_ACCESS_KEY_ID/"
              "R2_SECRET_ACCESS_KEY/R2_BUCKET absent and no --from-dir) — "
              f"no session record written for {sess}")
        return {"ok": True, "session_date": sess, "roots": [], "reason": "no_archive_source"}

    tide_doc = reader.tide(sess)
    dte_doc = reader.dte_tide(sess)
    if tide_doc is None or dte_doc is None:
        _warn("session_digest",
              f"{sess}: dated tape archives absent (tide={'yes' if tide_doc else 'no'}, "
              f"dte_tide={'yes' if dte_doc else 'no'}) — records print the gap in plain "
              "words instead of a number")

    candidates = [r.upper() for r in (roots or configured_roots())]
    covered, promised = discover_roots(reader, candidates, sess)

    records: list[dict] = []
    for r in covered:
        try:
            rec = digest_root(reader, root=r, session_date=sess, site=site, data=data,
                              tide_doc=tide_doc, dte_doc=dte_doc,
                              scan_spots=scan_spots, workers=workers,
                              listed=(r in promised))
        except Exception as e:  # noqa: BLE001 — one bad root never costs the others
            _warn("session_digest", f"{r} {sess}: digest failed ({e})")
            continue
        if rec is None:
            log.info("session_digest: %s has no archived session for %s", r, sess)
            continue
        records.append(rec)

    if not records:
        _warn("session_digest",
              f"{sess}: no root had a readable intraday archive (tried "
              f"{', '.join(candidates) or 'none'}) — nothing written")
        return {"ok": True, "session_date": sess, "roots": [],
                "reason": "no_archived_roots", "r2_gets": reader.gets,
                "seconds": round(_time.monotonic() - t0, 2)}

    # Lane law (§0.9): `data/` belongs to the nightly lane ALONE — both the dated records and
    # the forward ledger.  An off-lane run (intraday probe, replay, fastpath) still refreshes
    # the display artifact under `site/`, because that is a latest-pointer a surface reads and
    # not a record anyone grades; it writes nothing under `data/`.
    nightly = nightly_advance_enabled()
    written: list[str] = []
    data_written: list[str] = []
    if not dry_run:
        for rec in records:
            if nightly:
                _write_json_atomic(data / "options_session" / sess / f"{rec['root']}.json", rec)
                data_written.append(rec["root"])
            if write_latest(site, rec) is not None:
                written.append(rec["root"])
        if not nightly:
            log.info("session_digest: data/ writes skipped for %d root(s) "
                     "(COLLECT_LANE != nightly) — site/session latest still refreshed",
                     len(records))
    ledger_rows = append_ledger(data, [sd.ledger_row(r) for r in records]) if not dry_run else -1

    secs = round(_time.monotonic() - t0, 2)
    log.info("session_digest: %s — %d root(s) %s, %d R2 get(s), %.2fs",
             sess, len(records), ",".join(r["root"] for r in records), reader.gets, secs)
    return {
        "ok": True,
        "session_date": sess,
        "roots": [r["root"] for r in records],
        "written": written,
        "ledger_rows": ledger_rows,
        "r2_gets": reader.gets,
        "r2_misses": reader.misses,
        "seconds": secs,
        "coverage": {r["root"]: r["coverage"]["quality_en"] for r in records},
    }


def _selftest() -> int:
    """Offline shape check: a synthetic two-stamp archive digests without a network."""
    frame = {
        "root": "TEST", "session_date": "2026-07-28", "asof": "2026-07-28T20:00:00Z",
        "cadence": "5m", "metrics": ["netprem"],
        "price_levels": [500.0, 505.0, 510.0],
        "time_steps": ["09:30", "09:35", "09:40", "09:45", "09:50", "09:55", "10:00"],
        "grids": {"netprem": [
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
            [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        ]},
    }
    rec = sd.build_session_record(
        root="TEST", session_date="2026-07-28", asof="now", frame=frame,
        stamps=["0930", "0935", "0940", "0945", "0950", "0955", "1000"],
        cadence_sec=300, spots_by_stamp={}, levels=None, dte_doc=None, tide_doc=None)
    assert rec["schema"] == sd.SCHEMA, rec["schema"]
    assert rec["arc"] and rec["arc"][-1]["t"] == "10:00"
    assert rec["coverage"]["minutes"] == 7
    assert rec["coverage"]["quality_en"], "coverage must speak in plain words"
    assert sd.ledger_row(rec)["root"] == "TEST"
    print("session_digest selftest OK", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="OIP E1 session digest (data only)")
    ap.add_argument("--date", default=None, help="session date YYYY-MM-DD (default: last session)")
    ap.add_argument("--roots", default=None, help="comma-separated roots (default: config/defaults)")
    ap.add_argument("--from-dir", default=None,
                    help="read archives from a local directory instead of R2 (replay)")
    ap.add_argument("--dry-run", action="store_true", help="derive and report, write nothing")
    ap.add_argument("--no-spot-scan", action="store_true",
                    help="skip the per-stamp spot scan (no level-crossing events)")
    ap.add_argument("--workers", type=int, default=SPOT_SCAN_WORKERS)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest()
    try:
        res = run(
            session_date=a.date,
            roots=[r.strip() for r in a.roots.split(",") if r.strip()] if a.roots else None,
            from_dir=Path(a.from_dir) if a.from_dir else None,
            dry_run=bool(a.dry_run),
            scan_spots=not a.no_spot_scan,
            workers=a.workers,
        )
        print(json.dumps(res, ensure_ascii=False, indent=1), flush=True)
    except Exception as e:  # noqa: BLE001 — a builder never breaks the nightly
        _warn("session_digest", f"unhandled failure: {e}")
        log.warning("session_digest traceback", exc_info=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
