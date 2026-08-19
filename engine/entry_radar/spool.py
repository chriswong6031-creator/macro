"""engine/entry_radar/spool.py — the durable prospective nomination spool.

WHY THIS EXISTS AT PR-1 AND NOT PR-5
------------------------------------
Two of Radar's highest-value nomination producers are **ephemeral**: the 5-min
``engine/marketing/hot_tape.py`` detector writes no ``data/`` artifact at all
(only a marketing outbox), and ``build_intraday_flow.py --mode fastpath`` writes
zero ``data/`` by design (HOUSE-U5).  Their history is therefore
**unreconstructible after the fact** — there is no vintage to replay
(contract §5 leakage matrix, ephemeral-producers row; §11 Q4).

So the record has to be made *as it happens*, from day one, before any detector
or episode exists to consume it.  Every ingested nomination event is appended
here at ingestion.  A nomination that was never spooled may never enter an
episode later — that is the "spool-before-consume" test.

WRITE TARGET — NEVER ``data/``
------------------------------
Convention SHAPE copied from the prophet-live R2 plane
(``engine/prophet_live/r2io.py``): **one object per pass-with-events**, keyed
``live_flow/entry_radar_nominations/<YYYY-MM-DD>/<HHMMSS>.json``, never
read-modify-write — two passes can never both be holding the day's file, so no
row can be lost to the shared-``.tmp`` erasure class.  The module is a *shape*
copy rather than an import: this package stays a leaf with no Prophet-side
imports (contract §16 non-interference (a)).

Backends, in order: R2 when credentials exist, else a local directory
(``$ENTRY_RADAR_SPOOL_DIR``) — which is what tests use.  Neither is under
``data/``: the nightly reconciler of PR-5 is the only durable ``data/`` writer.

``ENTRY_RADAR_NO_PUBLISH=1`` refuses every write with a line-start annotation.
Set it in any rehearsal or demo that runs the real lane end to end — the spool
is the forward ledger's raw input, and a fabricated row joined to real closes is
indistinguishable from a genuine one forever (the prophet-live precedent).

HOT-TAPE TAP — WHY IT LIVES HERE
---------------------------------
``tap_hot_tape_events`` is in the spool module rather than ``producers/``
because hot_tape is the one producer with **no artifact to adapt**: its
nomination does not exist unless it is captured at emission and spooled in the
same breath.  The tap is a pure function the marketing lane *could* call; this
PR does not modify ``engine/marketing/hot_tape.py``.

    FOLLOW-UP (one line, PR-4 wiring, deliberately not taken in PR-1):
    in ``engine/marketing/hot_tape.py``'s ``detect_events()`` caller
    (``scripts/hot_tape_radar.py``), after events are computed, add

        from engine.entry_radar.spool import spool_hot_tape          # noqa
        spool_hot_tape(events, source_asof=<merge ts>)

    That is the whole integration.  It is out of scope here because the hard
    laws for this PR forbid edits outside the Radar-owned paths, and because a
    tap on a 5-min marketing lane wants its own review.

Until that wiring lands, ``tail_outbox_events`` is the PROSPECTIVE fallback: it
reads the marketing outbox (``data/marketing/outbox/*.json`` — a READ, this
package writes no ``data/`` path) and recovers ticker mentions from posts
already emitted.  It is strictly weaker than the tap (the outbox carries what
was *published*, not what was *detected*) and is labelled ``data_quality =
degraded`` for exactly that reason.

READ-SIDE SEAM (LAB-0 §6, added for the Prophet Operator Lab's commissioning
prep — never a second R2 client)
------------------------------------------------------------------------------
``r2_credentials_present``/``r2_client_for_read``/``r2_bucket_name``/
``list_r2_keys``/``get_r2_object_bytes``, just above :class:`NominationSpool`,
are a public wrapper onto the exact credential/client logic ``_put`` already
builds, plus a minimal list/get pair — extracted so
``engine.prophet_lab.sources`` (an injectable-root READER of this module's
own event-spool output) can resolve the identical R2-first-else-local ladder
without duplicating credential handling or building a second client. The
WRITE path (``NominationSpool``/``EventSpool``) is unchanged by this addition.
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from engine.entry_radar.contracts import (
    AUTHORITY_BLOCK,
    NOMINATION_SCHEMA,
    Nomination,
    NominationError,
    ProducerRead,
    iso,
    parse_ts,
    utcnow,
)

log = logging.getLogger(__name__)

SPOOL_PREFIX = "live_flow/entry_radar_nominations"
SPOOL_SCHEMA = "mastermind.entry_probe_nomination_spool.v1"

_NO_PUBLISH_ENV = "ENTRY_RADAR_NO_PUBLISH"
_SPOOL_DIR_ENV = "ENTRY_RADAR_SPOOL_DIR"


def _no_publish() -> bool:
    return os.environ.get(_NO_PUBLISH_ENV, "").strip() not in ("", "0", "false")


def spool_key(session: str, stamp: str, *, prefix: str = SPOOL_PREFIX,
              pass_id: str = "") -> str:
    """``<prefix>/<YYYY-MM-DD>/<HHMMSS>-<pass_id>.json`` — one object per pass.

    ``pass_id`` is part of the key because two lanes can spool inside the same
    SECOND (the nightly assembly and a hot_tape tap, say), and a bare HHMMSS key
    would have the second write silently overwrite the first — losing durable
    nomination events with no error anywhere.  Object-per-pass only protects the
    record if the object name is actually unique per pass.
    """
    # Underscores survive: they are filename-safe and keep the key readable as
    # the producer id it came from (``hot_tape``, not ``hot-tape``).
    slug = re.sub(r"[^a-z0-9_]+", "-", str(pass_id or "pass").lower()).strip("-_") or "pass"
    return f"{prefix}/{session}/{stamp}-{slug}.json"


def _bucket() -> str:
    return os.environ.get("R2_BUCKET", "mastermindx").strip() or "mastermindx"


def _r2_client():
    """S3 client for R2, or None when credentials are absent (graceful no-op).

    Shape copy of ``scripts/publish_r2.py::_client`` / prophet-live's ``r2io``,
    including the botocore checksum workaround (R2 rejects the default CRC32
    trailer).  boto3 is imported LAZILY so every test lane imports this module
    without it.
    """
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
        kw: dict[str, Any] = dict(region_name="auto", signature_version="s3v4",
                                  max_pool_connections=8,
                                  retries={"max_attempts": 4, "mode": "standard"},
                                  connect_timeout=15, read_timeout=60)
        try:
            cfg = Config(**kw, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                            aws_secret_access_key=sk, config=cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning("entry_radar.spool: R2 client build failed: %s", exc)
        return None


def local_spool_dir() -> Path | None:
    """``$ENTRY_RADAR_SPOOL_DIR`` when set.  Never a ``data/`` path."""
    raw = os.environ.get(_SPOOL_DIR_ENV, "").strip()
    return Path(raw) if raw else None


# ---------------------------------------------------------------------------
# READ-side seam — reused by engine.prophet_lab.sources, never a second R2
# client (LAB-0 §6 R-LAB-1 sibling scope: "the same backend ladder the Radar
# spool WRITER uses").  These four functions are the entire extraction: a
# public wrapper onto the exact credential/client logic ``_put`` already
# builds for writes, plus a list/get pair with the identical "raise, never
# swallow" discipline a READER needs (a caller that silently ate a
# ListBucket/GetObject permission error would show an empty-and-clean board
# instead of the visible health state LAB-0 requires). Nothing about the
# WRITE path (``NominationSpool``/``EventSpool``) changes.
# ---------------------------------------------------------------------------
def r2_credentials_present() -> bool:
    """Cheap presence check for the three R2 env vars, no client build.

    Lets a caller distinguish "no R2 credentials configured at all" (the
    ordinary local-dev/CI case) from "credentials present but the client/list
    call itself failed" without paying for a client build just to answer the
    first question.
    """
    return bool(
        os.environ.get("R2_ENDPOINT")
        and os.environ.get("R2_ACCESS_KEY_ID")
        and os.environ.get("R2_SECRET_ACCESS_KEY")
    )


def r2_client_for_read() -> Any:
    """Public seam onto :func:`_r2_client` — the identical client every spool
    write already builds (same endpoint/keys/checksum-workaround config).  A
    reader must resolve the SAME backend, not a second, divergently
    configured one.  Returns ``None`` when credentials are absent; never
    raises (matches ``_r2_client``'s own contract).
    """
    return _r2_client()


def r2_bucket_name() -> str:
    """Public seam onto :func:`_bucket` — the bucket every spool write/read
    resolves to (``$R2_BUCKET``, default ``mastermindx``)."""
    return _bucket()


def list_r2_keys(s3: Any, prefix: str, *, bucket: str | None = None) -> list[str]:
    """Every object key under ``prefix``, paginated via ``list_objects_v2``.

    Deliberately RAISES on a genuine R2 error rather than swallowing it —
    the one property a reader needs that a writer does not: a
    credential/permission/network failure must reach the caller as a named
    fact, never as a silently-empty (and therefore falsely "clean") list.
    Manual ``ContinuationToken`` pagination (not ``get_paginator``) so a test
    double only needs to implement ``list_objects_v2`` itself, matching the
    plain-method fakes already used against this module's write side
    (``tests/test_entry_radar_w4_lane.py``'s ``ExplodingR2``).
    """
    keys: list[str] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket or _bucket(), "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or ():
            key = obj.get("Key")
            if key:
                keys.append(key)
        if resp.get("IsTruncated") and resp.get("NextContinuationToken"):
            token = resp["NextContinuationToken"]
            continue
        break
    return keys


def get_r2_object_bytes(s3: Any, key: str, *, bucket: str | None = None) -> bytes:
    """One object's body.  Same never-swallow discipline as :func:`list_r2_keys`."""
    resp = s3.get_object(Bucket=bucket or _bucket(), Key=key)
    body = resp["Body"]
    return body.read() if hasattr(body, "read") else bytes(body)


class NominationSpool:
    """Append-only spool of nomination events.  R2 first, local dir as fallback.

    ``sink`` is injectable so the assembly lane can be tested end-to-end without
    R2 credentials and without touching the filesystem at all.
    """

    def __init__(self, *, s3: Any = None, local_dir: Path | None = None,
                 prefix: str = SPOOL_PREFIX) -> None:
        self.prefix = prefix
        self._s3 = s3
        self._local = local_dir if local_dir is not None else local_spool_dir()
        self.written_keys: list[str] = []

    # -- backend ----------------------------------------------------------
    def _put(self, key: str, payload: dict[str, Any]) -> bool:
        try:
            body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            print(f"::warning title=entry-radar-spool::{key} payload is not JSON-safe "
                  f"({exc}) — nomination events NOT spooled", flush=True)
            return False

        s3 = self._s3 if self._s3 is not None else _r2_client()
        if s3 is not None:
            try:
                s3.put_object(Bucket=_bucket(), Key=key, Body=body,
                              ContentType="application/json")
                log.info("entry_radar.spool: published %s (%d bytes)", key, len(body))
                self.written_keys.append(key)
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"::warning title=entry-radar-spool::R2 PUT {key} failed ({exc}) — "
                      f"falling back to the local spool", flush=True)

        if self._local is not None:
            path = self._local / key
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".json.tmp")
                tmp.write_bytes(body)
                os.replace(tmp, path)
                self.written_keys.append(key)
                return True
            except OSError as exc:
                print(f"::warning title=entry-radar-spool::local spool write {path} failed "
                      f"({exc}) — nomination events NOT durable", flush=True)
                return False

        # Distinguish "never had a sink" from "the sink we had rejected the write":
        # the second is an incident, and reporting it as missing credentials would
        # send the operator to the wrong place.
        why = ("the R2 PUT failed and no local fallback is configured"
               if (self._s3 is not None or _r2_client() is not None)
               else f"no R2 credentials and no ${_SPOOL_DIR_ENV}")
        print(f"::warning title=entry-radar-spool::{why} — {key} NOT spooled; "
              "ephemeral-producer nominations from this pass are unreconstructible",
              flush=True)
        return False

    # -- api --------------------------------------------------------------
    def append(self, nominations: Sequence[Nomination], *,
               producers: Sequence[ProducerRead] = (),
               now: datetime | None = None,
               pass_id: str = "") -> str | None:
        """Spool one pass.  Returns the key written, or None.

        A pass with **zero** nominations writes nothing (one object per
        pass-*with-events*), but a pass whose producers were all unavailable
        DOES write — an outage is a fact worth keeping, and its absence is
        exactly what would later read as "nothing happened".
        """
        stamp_at = now or utcnow()
        unavailable = [p for p in producers if p.status == "unavailable"]
        if not nominations and not unavailable:
            return None
        if _no_publish():
            print(f"::warning title=entry-radar-spool::{_NO_PUBLISH_ENV} is set — refusing "
                  f"to spool {len(nominations)} nomination event(s)", flush=True)
            return None

        session = stamp_at.astimezone(timezone.utc).date().isoformat()
        stamp = stamp_at.astimezone(timezone.utc).strftime("%H%M%S")
        key = spool_key(session, stamp, prefix=self.prefix, pass_id=pass_id)
        payload = {
            "schema": SPOOL_SCHEMA,
            "nomination_schema": NOMINATION_SCHEMA,
            "authority": dict(AUTHORITY_BLOCK),
            "spooled_at": iso(stamp_at),
            "session": session,
            "pass_id": pass_id,
            "n_nominations": len(nominations),
            "producers": [p.to_dict() for p in producers],
            "nominations": [n.to_dict() for n in nominations],
        }
        return key if self._put(key, payload) else None


# ---------------------------------------------------------------------------
# hot_tape tap — the ephemeral producer with no artifact
# ---------------------------------------------------------------------------

HOT_TAPE_SOURCE_ID = "hot_tape:detect_events"
_HOT_TAPE_TTL_MIN = 90.0


def tap_hot_tape_events(events: Iterable[Any], *,
                        source_asof: datetime | None = None,
                        now: datetime | None = None,
                        ttl_minutes: float = _HOT_TAPE_TTL_MIN) -> list[Nomination]:
    """Convert ``engine.marketing.hot_tape.detect_events()`` output to nominations.

    A pure function over whatever the detector already holds in memory — dicts
    or objects, both accepted, since this PR does not touch hot_tape and must
    not assume its row type.  Recognised keys: ``ticker``/``sym``,
    ``kind``/``event``/``reason`` and ``change_pct``/``price``.

    ``source_asof`` is the live-quote merge timestamp; absent one, the tap falls
    back to ``now`` and marks ``data_quality = degraded`` — an unknown artifact
    vintage is a real degradation of PIT quality, and saying so is cheaper than
    inventing a vintage.
    """
    stamp = now or utcnow()
    asof = source_asof or stamp
    clamped = asof > stamp
    asof = min(asof, stamp)
    quality = "ok" if (source_asof is not None and not clamped) else "degraded"
    ttl = stamp + timedelta(minutes=max(1.0, ttl_minutes))
    out: list[Nomination] = []
    for ev in events or ():
        get = ev.get if isinstance(ev, dict) else (lambda k, d=None, _e=ev: getattr(_e, k, d))
        sym = get("ticker") or get("sym") or ""
        if not str(sym).strip():
            continue
        kind = str(get("kind") or get("event") or get("reason") or "move").strip() or "move"
        val = get("change_pct")
        try:
            value = float(val) if val is not None else None
        except (TypeError, ValueError):
            value = None
        try:
            out.append(Nomination(
                ticker=str(sym),
                source_id=HOT_TAPE_SOURCE_ID,
                source_family="news_catalyst",
                reason_code=f"hot_tape.{kind}",
                reason_text=f"Hot Tape 5-min detector flagged {str(sym).upper()} ({kind})",
                observed_at=stamp,
                source_asof=asof,
                source_value=value,
                source_horizon="intraday",
                ttl_until=ttl,
                evidence_ref="engine/marketing/hot_tape.py::detect_events",
                data_quality=quality,
            ))
        except NominationError as exc:
            log.warning("entry_radar.spool: hot_tape event skipped (%s)", exc)
    return out


def spool_hot_tape(events: Iterable[Any], *, source_asof: datetime | None = None,
                   spool: NominationSpool | None = None,
                   now: datetime | None = None) -> str | None:
    """The one-line integration the marketing lane would call.  See module docstring."""
    noms = tap_hot_tape_events(events, source_asof=source_asof, now=now)
    if not noms:
        return None
    return (spool or NominationSpool()).append(noms, now=now, pass_id="hot_tape")


def tail_outbox_events(outbox_dir: Path, *, since: datetime | None = None,
                       now: datetime | None = None,
                       limit: int = 500) -> ProducerRead:
    """PROSPECTIVE fallback: recover ticker mentions from the marketing outbox.

    A READ of ``data/marketing/outbox/*.json`` — this package writes no ``data/``
    path.  Strictly weaker than the tap above (the outbox carries what was
    *published*, not what was *detected*, and drops everything the poster
    filtered), so every nomination it yields is ``data_quality = degraded``.

    Returns ``unavailable`` when the directory is absent, which on the render
    host is the normal case — an absent outbox is not an absence of hot tape.
    """
    stamp = now or utcnow()
    if not outbox_dir.is_dir():
        return ProducerRead(source_id="hot_tape:outbox", status="unavailable",
                            observed_at=stamp,
                            detail=f"{outbox_dir} absent — outbox not readable on this host")
    noms: list[Nomination] = []
    newest: datetime | None = None
    try:
        paths = sorted(outbox_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError as exc:
        return ProducerRead(source_id="hot_tape:outbox", status="unavailable",
                            observed_at=stamp, detail=f"outbox listing failed: {exc}")
    for path in paths[:limit]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        asof = parse_ts(raw.get("ts") or raw.get("created_at") or raw.get("asof"))
        if asof is None:
            try:
                asof = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
        if since is not None and asof < since:
            continue
        newest = asof if newest is None else max(newest, asof)
        for sym in raw.get("tickers") or ([raw.get("ticker")] if raw.get("ticker") else []):
            if not str(sym or "").strip():
                continue
            try:
                noms.append(Nomination(
                    ticker=str(sym),
                    source_id="hot_tape:outbox",
                    source_family="news_catalyst",
                    reason_code="hot_tape.outbox_mention",
                    reason_text=f"{str(sym).upper()} named in a published Hot Tape post",
                    observed_at=stamp,
                    source_asof=min(asof, stamp),
                    source_horizon=("intraday" if asof <= stamp
                                    else "intraday(future-vintage-clamped)"),
                    ttl_until=stamp + timedelta(minutes=_HOT_TAPE_TTL_MIN),
                    evidence_ref=f"outbox:{path.name}",
                    data_quality="degraded",
                ))
            except NominationError as exc:
                log.warning("entry_radar.spool: outbox mention skipped (%s)", exc)
    return ProducerRead(source_id="hot_tape:outbox", status="ok",
                        nominations=tuple(noms), source_asof=newest, observed_at=stamp,
                        detail=f"{len(noms)} mention(s) from {len(paths)} outbox file(s)")
