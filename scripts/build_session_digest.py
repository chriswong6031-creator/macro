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
through `session_digest.clock_read`, which scores the whole label DISTRIBUTION against the
session window, declares itself ambiguous rather than guessing, and disarms itself once
`_minute_key` is repaired.  Fixing `_minute_key` is out of this builder's scope (it changes live
payload bytes and the Terminal's axis) and is filed separately.

DATE ARITHMETIC IS SESSION-DATE ARITHMETIC: gex_state stamps `datetime.now(UTC)` and the nightly
band runs after UTC midnight, so `asof[:10]` is D+1 for every real nightly run.  Vintages go
through `levels_vintage` → `lib.nyse_calendar.session_date`, never a UTC date slice.

READ SHAPE: the newest per-stamp frame already carries the FULL session (each file is the day
truncated to that stamp), so the arc/pace/pocket figures cost ONE object.  Only the price path
needs a request per stamp, and it is fetched as a ~256-byte RANGE read of each frame's head
rather than the whole file — fetching all frames in full is quadratic in bytes (measured 124.8 MB
for ONE root at the configured 120s cadence; the whole run costs 4.06 MB instead of 374 MB).
See `scan_session`.

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
import re
import sys
import tempfile
import time as _time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import session_digest as sd                     # noqa: E402
from engine.ledger_lane import nightly_advance_enabled      # noqa: E402
from lib import config, illus, nyse_calendar                # noqa: E402

log = logging.getLogger("build_session_digest")

# R2 prefixes — must match the writers verbatim (scripts/build_flow_surface.R2_SURFACE_PREFIX
# and scripts/live_flow_poller.R2_PREFIX).
R2_SURFACE_PREFIX = "live_flow/surface/"
R2_TIDE_PREFIX = "live_flow/tide/"
R2_DTE_TIDE_PREFIX = "live_flow/dte_tide/"

# Roots to try when nothing narrows the list.  Mirrors
# scripts/build_flow_surface.DEFAULT_SURFACE_ROOTS; config live_flow.surface_roots wins.
DEFAULT_ROOTS = ["SPY", "QQQ", "IWM"]

# Bytes fetched per stamp when scanning the price path.  `frame_for_stamp` writes `spot` as the
# FIRST key, so 256 bytes covers it with room for a long price_levels prefix to start.
HEAD_RANGE_BYTES = 256

# `"spot": <number|null>` inside the head bytes.  Byte-level so no decode is needed on a range
# read that may end mid-character.
#
# The trailing lookahead is load-bearing: without it a head that stopped mid-number matched the
# PREFIX and reported it as the value — b'{"spot":73' yielded 73 for a spot of 735.05, silently
# wrong by an order of magnitude and never falling back.  Requiring a JSON terminator means a
# truncated number simply does not match, and the full-fetch fallback runs instead.
_SPOT_HEAD_RE = re.compile(
    rb'"spot"\s*:\s*(null|-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?=[,}\s\]])')

# Exactly a YYYY-MM-DD directory name.  The record prune only ever considers these, so a stray
# file under data/options_session/ can never be deleted by it.
_SESSION_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Parallel range reads for the per-stamp spot scan.  A session is 196 stamps at the configured
# 120-second cadence, and the per-stamp spot lives ONLY inside each stamp's own frame
# (build_flow_surface's frame_for_stamp drops spot_path, and _full.json is staged locally but
# never uploaded), so the scan is one ~256-byte range read per stamp.  8 keeps the wall clock
# near a second without becoming a burst against R2 (measured: 602 reads / 4.06 MB / 1.2s for
# three roots).
SPOT_SCAN_WORKERS = 8

# Bounded walk-back when the newest stamp's frame will not load: the full-day arc lives in
# the LAST frame (each stamp file is the day truncated to that stamp), so a corrupt tail
# would otherwise cost the whole session.  3 attempts, then the root degrades honestly.
FRAME_FALLBACK_TRIES = 3

LEDGER_REL = "options_session/ledger.parquet"

# Internal wall-clock budget, seconds.  The engine job was CANCELLED at its 200-minute cap in 5
# of 8 recent nightlies, so a new step may not add unbounded tail risk: when R2 is slow the
# builder stops reading, writes what it has WITH the shortfall printed in the coverage block,
# and annotates.  Partial output that declares itself partial is worth more than a step that
# takes the whole deploy down with it.  daily.yml carries a `timeout-minutes` belt as well —
# this is the braces, and it is the one that still produces a record.
BUDGET_SECONDS = 180.0

# How many dated session directories to keep under data/options_session/.  These are committed
# git artifacts, so they accumulate forever without a sweep; the ledger parquet is the durable
# record and the dated JSONs are the working detail behind it.  40 sessions ~ two months, which
# covers any surface's "recent sessions" need with room to spare.
RECORD_RETAIN_SESSIONS = 40


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
        self.bytes_read = 0
        self.range_fallbacks = 0

    @property
    def live(self) -> bool:
        return bool(self.from_dir) or bool(self.s3 and self.bucket)

    def get_json(self, key: str) -> dict | None:
        """Fetch and parse one JSON object; None on absence or any parse/transport error."""
        self.gets += 1
        if self.from_dir is not None:
            p = self.from_dir / key
            try:
                self.bytes_read += p.stat().st_size
                return json.loads(p.read_text())
            except Exception:  # noqa: BLE001 — absence and corruption are the same answer
                self.misses += 1
                return None
        if not (self.s3 and self.bucket):
            self.misses += 1
            return None
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            body = resp["Body"].read()
            self.bytes_read += len(body)
            return json.loads(body)
        except Exception as e:  # noqa: BLE001
            self.misses += 1
            log.debug("session_digest: get %s failed: %s", key, e)
            return None

    def get_head_bytes(self, key: str, n: int | None = None) -> bytes | None:
        """First `n` bytes of an object, via an HTTP Range request.  None on any failure.

        Why ranges exist in this builder: a per-stamp surface frame is the session TRUNCATED to
        that stamp, so the files grow through the day and fetching all of them is quadratic in
        bytes — measured at 107 MB for one root at the configured 120-second cadence (196 stamps
        x ~600 strikes), i.e. ~321 MB a night for three roots. The only field the scan needs is
        `spot`, which `frame_for_stamp` writes FIRST, so a few hundred bytes per stamp replaces
        the whole file and the same scan costs ~50 KB per root.
        """
        n = int(n or HEAD_RANGE_BYTES)
        self.gets += 1
        if self.from_dir is not None:
            p = self.from_dir / key
            try:
                with open(p, "rb") as f:
                    b = f.read(n)
                self.bytes_read += len(b)
                return b
            except Exception:  # noqa: BLE001
                self.misses += 1
                return None
        if not (self.s3 and self.bucket):
            self.misses += 1
            return None
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key,
                                      Range=f"bytes=0-{max(1, int(n)) - 1}")
            b = resp["Body"].read()
            self.bytes_read += len(b)
            return b
        except Exception as e:  # noqa: BLE001
            self.misses += 1
            log.debug("session_digest: range get %s failed: %s", key, e)
            return None

    # ── keyed helpers (key shapes mirror the writers) ────────────────────────────
    def dates_index(self, root: str) -> dict | None:
        return self.get_json(f"{R2_SURFACE_PREFIX}{root.upper()}/dates.json")

    def session_index(self, root: str, session_date: str) -> dict | None:
        return self.get_json(f"{R2_SURFACE_PREFIX}{root.upper()}/{session_date}/idx.json")

    def stamp_frame(self, root: str, session_date: str, stamp: str) -> dict | None:
        return self.get_json(
            f"{R2_SURFACE_PREFIX}{root.upper()}/{session_date}/{stamp}.json")

    def stamp_spot(self, root: str, session_date: str,
                   stamp: str) -> tuple[float | None, bool]:
        """That stamp's `spot`, read from the head of its frame instead of the whole file.

        `spot` is the first key `frame_for_stamp` emits and `json.dump` preserves insertion
        order, so it lands within the first few dozen bytes.  That ordering is a WRITER detail
        rather than a contract, so a head that yields no parseable `spot` falls back to a full
        fetch for that one stamp and increments `range_fallbacks` — if the writer ever reorders
        its keys the builder gets slower and noisier, never wrong.
        """
        key = f"{R2_SURFACE_PREFIX}{root.upper()}/{session_date}/{stamp}.json"
        head = self.get_head_bytes(key)
        if head:
            m = _SPOT_HEAD_RE.search(head)
            if m:
                raw = m.group(1)
                # Present, even when the poller could not resolve a spot: a null spot on a real
                # object is covered tape with an unknown price, not a missing minute.
                return (None if raw == b"null" else sd.as_float(raw.decode())), True
        self.range_fallbacks += 1
        fr = self.get_json(key)
        if isinstance(fr, dict):
            return sd.as_float(fr.get("spot")), True
        return None, False

    def tide(self, session_date: str) -> dict | None:
        return self.get_json(f"{R2_TIDE_PREFIX}{session_date}.json")

    def dte_tide(self, session_date: str) -> dict | None:
        return self.get_json(f"{R2_DTE_TIDE_PREFIX}{session_date}.json")


# ── local store reads ────────────────────────────────────────────────────────────

def levels_vintage(asof: str | None) -> str | None:
    """The ET SESSION DATE a gex_state `asof` timestamp belongs to.

    NOT `asof[:10]`.  `build_gex_board` stamps `datetime.now(UTC)`, and the nightly engine band
    commits between roughly 03:11 and 03:54 UTC — which is 23:11–23:54 ET on the session day
    BEFORE.  Slicing the UTC date therefore reported the vintage as D+1 for every real nightly
    run, which made the same-session check fail every single night: `walls.close` was
    permanently null, the EOD fallback was dead on arrival, and the bilingual note asserted the
    level came "from the close of D+1" — a dated statement that was simply false.

    `nyse_calendar.session_date` is the house function for exactly this mapping (it keys off the
    ET calendar date, so 2026-07-30T03:27Z → 2026-07-29) and also folds a weekend/holiday
    timestamp back to the prior session.
    """
    if not asof:
        return None
    try:
        dt = datetime.fromisoformat(str(asof).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return nyse_calendar.session_date(dt).isoformat()


def read_levels(site: Path, root: str) -> dict | None:
    """EOD flip/wall map for a root from the gex_state payload, with its SESSION-date vintage.

    A payload that will not parse yields None rather than a partial map.
    """
    p = site / "options_structure" / "gex_state" / f"{root.upper()}.json"
    try:
        doc = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(doc, dict):
        return None
    asof = doc.get("asof")
    return {
        "flip": doc.get("gamma_flip"),
        "call_wall": doc.get("call_wall"),
        "put_wall": doc.get("put_wall"),
        "spot": doc.get("spot"),
        "vintage": levels_vintage(asof),
        "asof": asof,
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
    deadline: float | None = None,
) -> tuple[dict | None, str | None, dict[str, float | None], dict | None, list[str] | None]:
    """Read one root's session → (frame, its stamp, spots, open walls, stamps read).

    READ SHAPE, and why it is not "fetch every stamp".  Each per-stamp file is the session
    TRUNCATED to that stamp, so the newest one already carries the FULL day's time axis and
    net-premium grid — the arc, the pace series and the pockets all come from that single
    object.  Fetching every stamp in full is quadratic in bytes: measured 124.8 MB for ONE root
    at the configured 120-second cadence (196 stamps x ~600 strikes), 374 MB a night at three
    roots.  So the reads are:

        dates.json + idx.json                    2 small objects
        newest readable frame                    1 object, ~1.3 MB at cadence 120 — the whole day
        first stamp's frame                      1 small object, for the OPENING wall map
        per-stamp `spot`                         1 RANGE read each (~256 B), not the whole file

    Measured for three roots at the configured cadence: 602 reads, 4.06 MB, 1.2s — against
    374 MB if every frame were fetched in full.

    `frame_for_stamp` drops `spot_path` and emits only that stamp's own `walls`, and `_full.json`
    is staged locally by the poller but NEVER uploaded (`build_and_stage_surfaces` queues only
    idx/stamp/dates keys), so the price path genuinely exists nowhere but spread across the
    per-stamp objects — hence a request per stamp, but only a few hundred bytes of it.

    With `spot_scan` off, only the tail window plus the first stamp are fetched; level-crossing
    events are then simply absent and the record says so.  A stamp that will not load maps to
    None — a gap in the tape stays a gap.

    The fifth return value is the list of stamps whose object actually answered, or None when the
    scan was skipped (nothing was verified, so nothing may be claimed).  The dated indexes are
    best-effort — a stamp can be listed while its PUT failed — and coverage must count what was
    read, not what was promised.

    `deadline` is a monotonic wall-clock budget: once passed, the scan stops and returns what it
    has.  Partial output that says it is partial beats a job the engine band cancels at its cap.
    """
    stamps = sorted(stamps)
    tail = stamps[-FRAME_FALLBACK_TRIES:] if stamps else []

    # 1. The day itself: newest readable frame, walking back at most FRAME_FALLBACK_TRIES so a
    #    single corrupt tail object cannot cost the whole session.
    frame, frame_stamp = None, None
    for stamp in reversed(tail):
        fr = reader.stamp_frame(root, session_date, stamp)
        if isinstance(fr, dict) and fr.get("grids"):
            frame, frame_stamp = fr, stamp
            break

    # 2. The opening wall map (absent until the greek tap is armed).
    open_walls = None
    if stamps:
        open_frame = reader.stamp_frame(root, session_date, stamps[0])
        if isinstance(open_frame, dict):
            open_walls = open_frame.get("walls")

    # 3. The price path: one range read per stamp.
    spots: dict[str, float | None] = {}
    read: list[str] | None = None
    if spot_scan and stamps:
        def one(stamp: str) -> tuple[str, float | None, bool]:
            if deadline is not None and _time.monotonic() > deadline:
                return stamp, None, False      # budget spent: unverified, never "read"
            return (stamp, *reader.stamp_spot(root, session_date, stamp))

        answered: list[str] = []
        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
            for stamp, spot, present in ex.map(one, stamps):
                spots[stamp] = spot
                if present:
                    answered.append(stamp)
        read = sorted(answered)

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
    deadline: float | None = None,
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
        workers=workers, spot_scan=bool(scan_spots), deadline=deadline)
    if frame is None:
        _warn("session_digest",
              f"{root} {session_date}: no readable stamp frame ({len(stamps)} stamp(s) "
              "promised by the index) — record written with an empty arc")
    elif stamps and frame_stamp != stamps[-1]:
        # M9: the arc/pace/pocket figures now stop short of the last minute the index lists,
        # while events and coverage still span the full stamp list.  Two different axes in one
        # record is exactly the kind of thing that reads as agreement, so it is annotated here
        # and disclosed in the payload's own coverage words.
        _warn("session_digest",
              f"{root} {session_date}: newest readable snapshot is {frame_stamp}, not "
              f"{stamps[-1]} — premium totals cover fewer minutes than the event timeline "
              "(both counts printed in the record's coverage)")
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
            "surface_frame_is_last_stamp": bool(stamps and frame_stamp == stamps[-1]),
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
    # RULING (adversarial review, OIP W1): filmstrip_html does NOT belong on this
    # record. engine/session_digest.py's module docstring describes this shape as a
    # settled, replayable record — rendered SVG markup drifts from CSS and can never
    # be replayed. The SSR fragment (research/options_estate/W1_DESIGN_SPEC.md §3)
    # is display-tier only: run() (below) computes it fresh, on a COPY of this
    # record, immediately before write_latest() writes site/session/<ROOT>.json.
    # write_record() — the dated data/options_session/<date>/<root>.json ledger —
    # gets this exact record, unmodified, so the ledger keeps only the fields the
    # fragment is derived from (arc, coverage, events, flip), never the fragment.
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


def _minutes_of(doc: object) -> int:
    """`coverage.minutes` from a record, or -1 when it cannot be read."""
    if not isinstance(doc, dict):
        return -1
    m = ((doc.get("coverage") or {}) if isinstance(doc.get("coverage"), dict) else {}).get("minutes")
    try:
        return int(m)
    except (TypeError, ValueError):
        return -1


def write_record(data: Path, session_date: str, record: dict) -> Path | None:
    """Write the dated record unless one already on disk is a BETTER read of the same session.

    A settled record is a record.  Re-running the digest after the surface archive has aged past
    its 10-session retention re-reads a session that is mostly gone — measured: a re-run dropped
    `coverage.minutes` from 79 to 6 while the ledger (keep-first) still said 79, so the two
    artifacts disagreed about the same day and the JSON was the one that had degraded.  Weekends
    made it routine: three nightly runs all resolve to the same Friday.

    So a re-read replaces an existing record only when it is STRICTLY BETTER by covered minutes;
    ties and regressions keep what is already there.  That is the same keep-first spirit as the
    ledger, with an explicit exception for genuine improvement (a re-run after a poller backfill).
    """
    p = data / "options_session" / session_date / f"{record['root']}.json"
    if p.exists():
        try:
            have = _minutes_of(json.loads(p.read_text()))
        except Exception:  # noqa: BLE001 — an unreadable record is worse than any real read
            have = -1
        new = _minutes_of(record)
        if new <= have:
            log.info("session_digest: %s %s record kept (%d covered minute(s) on disk vs %d "
                     "in this read)", record["root"], session_date, have, new)
            return None
    return _write_json_atomic(p, record)


def write_latest(site: Path, record: dict) -> Path | None:
    """Write `site/session/{ROOT}.json` unless what is there is newer, or better for the same day.

    Two rules, both one-directional:
      * "Latest" only moves FORWARD — replaying an older date to backfill the ledger must not
        roll a live surface back to that older day.
      * For the SAME day it only improves — a thinner re-read of today (post-retention, or a
        budget-truncated run) must not replace a fuller one a surface is already serving.
    """
    p = site / "session" / f"{record['root']}.json"
    try:
        if p.exists():
            cur = json.loads(p.read_text())
            if isinstance(cur, dict):
                have = str(cur.get("session_date") or "")[:10]
                want = str(record["session_date"])[:10]
                if have and have > want:
                    log.info("session_digest: %s latest keeps %s (newer than %s)",
                             record["root"], have, want)
                    return None
                if have and have == want and _minutes_of(cur) >= _minutes_of(record):
                    log.info("session_digest: %s latest keeps its %s read (%d covered "
                             "minute(s) vs %d)", record["root"], have,
                             _minutes_of(cur), _minutes_of(record))
                    return None
    except Exception as e:  # noqa: BLE001
        log.debug("session_digest: latest read failed for %s: %s", record["root"], e)
    return _write_json_atomic(p, record)


def prune_records(data: Path, *, retain: int = RECORD_RETAIN_SESSIONS) -> list[str]:
    """Drop dated record directories beyond the newest `retain` sessions; return what went.

    The dated JSONs are committed git artifacts, so with no sweep they grow without bound while
    the ledger parquet — the durable record — stays small.  Only exact YYYY-MM-DD directories are
    ever considered, so a stray file under data/options_session/ can never be deleted by this.
    """
    base = data / "options_session"
    if not base.is_dir():
        return []
    dated = sorted((d for d in base.iterdir()
                    if d.is_dir() and _SESSION_DIR_RE.match(d.name)),
                   key=lambda d: d.name, reverse=True)
    dropped: list[str] = []
    for d in dated[max(0, int(retain)):]:
        try:
            for f in d.iterdir():
                f.unlink()
            d.rmdir()
            dropped.append(d.name)
        except OSError as e:
            log.debug("session_digest: prune of %s failed: %s", d, e)
    if dropped:
        log.info("session_digest: pruned %d dated record dir(s) beyond %d retained: %s",
                 len(dropped), retain, ", ".join(dropped))
    return dropped


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

def _summary(*, session_date: str, reader: "ArchiveReader | None" = None,
             t0: float, budget_seconds: float, records: list[dict] | None = None,
             written: list[str] | None = None, data_written: list[str] | None = None,
             pruned: list[str] | None = None, budget_skipped: list[str] | None = None,
             ledger_rows: int = -1, ok: bool = True, reason: str | None = None) -> dict:
    """One shape for EVERY return path.

    The early-exit paths used to omit keys the happy path published (`over_budget`,
    `budget_skipped`, `r2_mb`), so a consumer reading the summary hit KeyError on exactly the
    degraded nights it most needed to inspect.  Every field is present on every path, and
    `over_budget` is measured against the budget this run was GIVEN — not the module constant,
    which an operator override would have made a lie.
    """
    recs = records or []
    elapsed = _time.monotonic() - t0
    secs = round(elapsed, 2)
    return {
        "ok": ok,
        "reason": reason,
        "session_date": session_date,
        "roots": [r["root"] for r in recs],
        "written": written or [],
        "data_written": data_written or [],
        "pruned_sessions": pruned or [],
        "budget_skipped": budget_skipped or [],
        "ledger_rows": ledger_rows,
        "r2_gets": reader.gets if reader else 0,
        "r2_misses": reader.misses if reader else 0,
        "r2_mb": round(reader.bytes_read / 1e6, 3) if reader else 0.0,
        "range_fallbacks": reader.range_fallbacks if reader else 0,
        "seconds": secs,
        "over_budget": elapsed > float(budget_seconds),
        "coverage": {r["root"]: r["coverage"]["quality_en"] for r in recs},
    }


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
    budget_seconds: float = BUDGET_SECONDS,
) -> dict:
    """Digest one session for every covered root.  Returns a run summary; never raises."""
    t0 = _time.monotonic()
    # A non-positive budget means "read nothing new" — a legitimate operator lever for a night
    # where the engine band is already at its cap, and the shape the tests exercise.  It is not
    # a silent kill: every skipped root emits its own ::warning.
    deadline = t0 + float(budget_seconds)
    repo = Path(root_dir) if root_dir else config.ROOT
    cfg = config.load()["storage"]
    site = repo / cfg["site_dir"]
    data = repo / cfg["data_dir"]

    sess = str(session_date or default_session_date())
    try:
        d = sd.as_session_date(sess)
    except Exception:  # noqa: BLE001
        _warn("session_digest", f"unparseable --date {sess!r} — nothing digested")
        return _summary(session_date=sess, t0=t0, budget_seconds=budget_seconds,
                        ok=False, reason="bad_date")
    if not nyse_calendar.is_session(d):
        _warn("session_digest",
              f"{sess} is not an NYSE session — nothing digested (weekend/holiday guard)")
        return _summary(session_date=sess, t0=t0, budget_seconds=budget_seconds,
                        reason="not_a_session")

    reader = ArchiveReader(s3=_r2_client() if from_dir is None else None,
                           bucket=os.environ.get("R2_BUCKET"),
                           from_dir=from_dir)
    if not reader.live:
        _warn("session_digest",
              "no archive source available (R2_ENDPOINT/R2_ACCESS_KEY_ID/"
              "R2_SECRET_ACCESS_KEY/R2_BUCKET absent and no --from-dir) — "
              f"no session record written for {sess}")
        return _summary(session_date=sess, t0=t0, budget_seconds=budget_seconds,
                        reason="no_archive_source")

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
    budget_skipped: list[str] = []
    for r in covered:
        if _time.monotonic() > deadline:
            # Do not START a root there is no time to finish: a half-read root would publish a
            # coverage number that understates the archive rather than the tape.
            budget_skipped.append(r)
            continue
        try:
            rec = digest_root(reader, root=r, session_date=sess, site=site, data=data,
                              tide_doc=tide_doc, dte_doc=dte_doc,
                              scan_spots=scan_spots, workers=workers,
                              listed=(r in promised), deadline=deadline)
        except Exception as e:  # noqa: BLE001 — one bad root never costs the others
            _warn("session_digest", f"{r} {sess}: digest failed ({e})")
            continue
        if rec is None:
            log.info("session_digest: %s has no archived session for %s", r, sess)
            continue
        records.append(rec)

    if budget_skipped:
        _warn("session_digest",
              f"{sess}: read budget spent before {', '.join(budget_skipped)} could be read — "
              "no record written for those roots this run")
    if not records:
        _warn("session_digest",
              f"{sess}: no root had a readable intraday archive (tried "
              f"{', '.join(candidates) or 'none'}) — nothing written")
        return _summary(session_date=sess, reader=reader, t0=t0,
                        budget_seconds=budget_seconds, budget_skipped=budget_skipped,
                        reason="no_archived_roots")

    # Lane law (§0.9): `data/` belongs to the nightly lane ALONE — both the dated records and
    # the forward ledger.  An off-lane run (intraday probe, replay, fastpath) still refreshes
    # the display artifact under `site/`, because that is a latest-pointer a surface reads and
    # not a record anyone grades; it writes nothing under `data/`.
    nightly = nightly_advance_enabled()
    written: list[str] = []
    data_written: list[str] = []
    pruned: list[str] = []
    if not dry_run:
        for rec in records:
            if nightly and write_record(data, sess, rec) is not None:
                data_written.append(rec["root"])
            # RULING: filmstrip_html is display-tier only (see digest_root's own
            # note above) — computed here, on a shallow copy, so the ledger write
            # above never sees it. One render per record either way (same cost
            # as before, just relocated to the write that actually needs it).
            display_rec = dict(rec)
            display_rec["filmstrip_html"] = illus.session_filmstrip(rec)
            if write_latest(site, display_rec) is not None:
                written.append(rec["root"])
        if not nightly:
            log.info("session_digest: data/ writes skipped for %d root(s) "
                     "(COLLECT_LANE != nightly) — site/session latest still refreshed",
                     len(records))
    ledger_rows = append_ledger(data, [sd.ledger_row(r) for r in records]) if not dry_run else -1
    if nightly and not dry_run:
        pruned = prune_records(data)

    out = _summary(session_date=sess, reader=reader, t0=t0, budget_seconds=budget_seconds,
                   records=records, written=written, data_written=data_written,
                   pruned=pruned, budget_skipped=budget_skipped, ledger_rows=ledger_rows)
    if out["over_budget"]:
        _warn("session_digest",
              f"{sess}: read budget of {float(budget_seconds):.0f}s was spent "
              f"({out['seconds']:.0f}s) — records written from the tape that had arrived, with "
              "the shortfall printed in their coverage")
    log.info("session_digest: %s — %d root(s) %s, %d read(s) / %.2f MB, %.2fs",
             sess, len(records), ",".join(r["root"] for r in records), reader.gets,
             reader.bytes_read / 1e6, out["seconds"])
    return out


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
    ap.add_argument("--budget-seconds", type=float, default=BUDGET_SECONDS,
                    help="wall-clock read budget; past it the run writes what it has")
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
            budget_seconds=a.budget_seconds,
        )
        print(json.dumps(res, ensure_ascii=False, indent=1), flush=True)
    except Exception as e:  # noqa: BLE001 — a builder never breaks the nightly
        _warn("session_digest", f"unhandled failure: {e}")
        log.warning("session_digest traceback", exc_info=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
