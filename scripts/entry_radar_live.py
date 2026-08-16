#!/usr/bin/env python3
"""scripts/entry_radar_live.py — the 5-minute RTH evaluator entrypoint (W4/PR-4).

WHAT THIS LANE OWNS
--------------------
Host wiring, and nothing else.  Every decision that could change a reading lives
in :mod:`engine.entry_radar.live_eval`, which is pure and injectable; this script
resolves WHERE things are, takes the lock, hands the evaluator its inputs and
publishes what comes back.  The split is deliberate: a pass has to be replayable
from a fixture for the PIT battery to mean anything, and it cannot be if the
evaluator reads a clock or opens a file for itself.

    python -m scripts.entry_radar_live [--dry-run] [--now ISO] [--state-dir P]

WHERE IT RUNS (W4 design §3, §3b)
----------------------------------
The VPS systemd timer ``macro-live-entry-radar.timer`` is the product lane;
``.github/workflows/entry-radar-live.yml`` is a self-disabling backstop.  GitHub
throttles this repo's frequent crons far past their documented cadence — a
5-minute product schedule is not purchasable there at any price (the measured
prophet-live finding, quoted rather than re-discovered) — so the workflow stands
down while ``vars.VPS_LIVE_PRIMARY`` is true and exists for a rebuild window.

QUOTE SOURCE (§3b census pin).  The box's own live plane, freshest-wins, through
``engine.marketing.live_verify``'s OWN merge helpers rather than a second reader:

  1. ``/var/lib/macro-live/state/quotes_full.json`` — the ~2,100-symbol universe
     the 5-minute snapshot lane publishes.  This is the COVERAGE source.
  2. ``/var/lib/macro-live/public/live/quotes.json`` — the ~34-symbol display set
     the 60-second fast lane publishes.  Fresher, and on its own nearly empty
     against a ~1,500-name probe set.

Radar fetches NO quotes of its own.  A probe name absent from the merge is
``unavailable`` and counted, never dropped (PIT-W4-17) — widening the shared
snapshot universe is a flagged follow-up owned by the quote lanes, not a Radar
edit.  Absent a local plane the script falls back to the estate merge, which is
what makes a GitHub-runner pass possible at all.

LEDGER LAW.  This lane writes NO ``data/`` path and runs no git command.  Three
sinks, none of them durable evidence: the runtime state dir (journal, ledger,
heartbeat, bucket cache), the R2/local event spool, and the served payload on the
VPS live plane.  ``ENTRY_RADAR_NO_PUBLISH`` refuses the spool AND the served copy
— the spool half is enforced by ``spool.NominationSpool._no_publish()``, not by
anything in this file, and :func:`publish` below is the served half.

THE PAYLOAD IS AUTH-GATED BY OMISSION (§3b).  ``live/entry_radar.json`` is
deliberately absent from Caddy's public allowlist, so the default-deny route
covers it.  Naming which probe names are armed and which are turning today is
pre-publication board membership; #3391 — the ruling that regwalled
``/factordata/*`` — is exactly about that.  Do not add it to the allowlist.

EXIT CODES (the spirit of ``scripts/entry_radar_live_pack.py``'s, extended)
---------------------------------------------------------------------------
  0  the pass completed — evaluated, or stood down cleanly (out of window,
     killed), or ``--dry-run``, or a ``ENTRY_RADAR_NO_PUBLISH`` rehearsal
  2  refusal BEFORE any evaluation — detector spec-hash drift
  3  the pass produced no output at all (nothing was published anywhere)
  4  spool failure — transitions withheld, ledger NOT committed, retried next
     pass (the addresses are deterministic, so the retry is once-effective)
  5  the pack cannot be evaluated against — absent, built for the wrong session,
     or ``proof_failed``; the whole cycle is refused per §5's stale-pack row
  6  the pass RAISED — the ``failed`` receipt was published in place of a result
     and the transitions of this pass, if any, were never admitted

3 AND 6 ARE DIFFERENT FACTS.  "Nothing was published" is a sink problem — the
evaluation may have been perfect.  A rehearsal with ``ENTRY_RADAR_NO_PUBLISH``
set therefore exits 0 and not 3: refusing to write is the point of the switch,
and reddening every rehearsal on a documented refusal trains an operator to
ignore the code that means a real publish failed.

A pass that fails for an UNEXPECTED reason exits 6 AND PUBLISHES THE ``failed``
RECEIPT.  It used to exit 0 in silence, which left the previous artifact in
place with its previous ``health.pass.at`` — stale but whole, so the only alarm
was the freshness sentinel, pinned at SESSION grain.  A persistent per-name
defect could therefore burn a full session green.  The receipt is the honest
alternative: the artifact says ``failed`` and names the exception, and a nonzero
exit puts it on the unit's own status too.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
# UNCONDITIONAL, position 0 — the conditional `if _CODE_ROOT not in sys.path`
# shape is not a pin: when the root is already on the path BEHIND a foreign
# package, the guard skips the insert and the foreign package still wins the
# import (tests/test_check_script_import_pinning.py::_strong_pin; the same
# comment rides scripts/entry_radar_universe.py and entry_radar_live_pack.py).
sys.path.insert(0, _CODE_ROOT)

from engine.entry_radar import live_eval as LE  # noqa: E402
from engine.entry_radar import live_ledger as LL  # noqa: E402
from engine.entry_radar import live_pack as LP  # noqa: E402

ROOT = Path(_CODE_ROOT)
log = logging.getLogger("entry_radar_live")

#: The VPS live plane, preference order — the SAME two files prophet-live reads.
#: Both, and the order is load-bearing: the display set alone would evaluate
#: almost none of the probe set and dark the rest ``no_quote`` — fresher, and
#: empty.  They are merged freshest-wins through ``live_verify``'s own
#: ``_merge_quotes`` so "which quote is newer" keeps one definition estate-wide.
LOCAL_QUOTE_PATHS: tuple[str, ...] = (
    "/var/lib/macro-live/state/quotes_full.json",
    "/var/lib/macro-live/public/live/quotes.json",
)

_STATE_DIR_ENV = "ENTRY_RADAR_STATE_DIR"
_VPS_STATE_DIR = Path("/var/lib/macro-live/state/entry_radar")
_VPS_LIVE_DIR = Path("/var/lib/macro-live/public/live")
_NO_PUBLISH_ENV = "ENTRY_RADAR_NO_PUBLISH"

#: The served artifact.  NOT in Caddy's public allowlist — see the docstring.
PAYLOAD_NAME = "entry_radar.json"

#: Orchestrator-lane convention: one flock BESIDE the state dir (design §3b —
#: ``state/entry_radar.lock`` next to ``state/entry_radar/``), so two timers
#: firing close together cannot both derive and both spool the same pass.
#:
#: A host with NO state plane takes no lock, and that is correct rather than a
#: gap: without a state dir there is no journal, no ledger and no bucket cache to
#: race over — every structure is in-memory and dies with the process — and the
#: payload write is an atomic rename either way.  The only shared resource left
#: is the spool, whose addresses are deterministic, so a doubled pass writes the
#: same object twice rather than two conflicting ones.
LOCK_NAME = "entry_radar.lock"

#: Durable ``data/`` paths this script writes.  EMPTY BY DESIGN.
DURABLE_WRITES: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# sinks
# ---------------------------------------------------------------------------

def state_dir(override: str | None = None) -> Path | None:
    """``--state-dir`` → ``$ENTRY_RADAR_STATE_DIR`` → the VPS path, or None.

    None means "no state plane on this host".  The pass still evaluates — it
    simply has no journal to replay, no ledger to advance and nothing that
    survives the process — which is exactly the GitHub-backstop case.
    """
    if override and override.strip():
        return Path(override.strip())
    env = os.environ.get(_STATE_DIR_ENV, "").strip()
    if env:
        return Path(env)
    return _VPS_STATE_DIR if _VPS_STATE_DIR.parent.is_dir() else None


def live_dir(root: Path, override: str | None = None) -> Path:
    """Resolve the live-artifact directory (contract §7.3 ladder)."""
    if override and override.strip():
        return Path(override.strip())
    env = os.environ.get("MACRO_LIVE_DIR", "").strip()
    if env:
        return Path(env)
    if _VPS_LIVE_DIR.is_dir():
        return _VPS_LIVE_DIR
    return root / "site" / "live"


def no_publish() -> bool:
    return os.environ.get(_NO_PUBLISH_ENV, "").strip() not in ("", "0", "false")


# ---------------------------------------------------------------------------
# quotes — live_verify's own helpers, never a second reader
# ---------------------------------------------------------------------------

def _read_local_json(path: Path) -> dict | None:
    """One local quote file, or None.  A CORRUPT file warns; an ABSENT one does not.

    The distinction is the whole point: no file means this host has no live plane
    (every CI runner, every dev checkout), which is normal.  A file that exists
    and will not parse means the plane is there and broken, which is not.
    """
    try:
        if not path.is_file():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=entry-radar-live::local quote file {path} unreadable "
              f"({exc}) — falling back to the merged quote view", flush=True)
        return None


def load_local_quotes(paths: tuple[str, ...] = LOCAL_QUOTE_PATHS) -> dict | None:
    """The local plane in ``load_live_quotes`` shape, or None when it has nothing.

    Built on ``live_verify``'s own private helpers rather than a second reader:
    the shape of a quote artifact, which quote wins a tie, and what a feed's
    declared delay means are estate-wide definitions, and a private copy of them
    here is how two surfaces end up disagreeing about the same tape.
    """
    from engine.marketing import live_verify as LV  # noqa: PLC0415

    quotes: dict[str, dict] = {}
    asof: str | None = None
    asof_ms: float | None = None
    used: list[str] = []
    feed_delay = 0.0
    for raw in paths:
        obj = _read_local_json(Path(raw))
        if not obj:
            continue
        got = LV._quotes_from_snapshot(obj)  # noqa: SLF001
        if not got:
            continue
        obj_ms = LV._artifact_ms(obj)  # noqa: SLF001
        LV._merge_quotes(quotes, got, obj_ms)  # noqa: SLF001
        used.append(Path(raw).name)
        feed_delay = max(feed_delay, LV._feed_delay_min(obj))  # noqa: SLF001
        if obj_ms is not None and (asof_ms is None or obj_ms > asof_ms):
            asof, asof_ms = obj.get("asof"), obj_ms
        elif asof is None:
            asof = obj.get("asof") or asof
    if not quotes:
        return None
    return {"quotes": quotes, "asof": asof, "source": "vps_local",
            "feed_delay_min": feed_delay, "local_files": used}


def load_quotes(root: Path) -> dict[str, Any]:
    """The local plane if it has anything, else the estate merge."""
    local = load_local_quotes()
    if local is not None:
        return local
    from engine.marketing import live_verify as LV  # noqa: PLC0415
    return LV.load_live_quotes(root)


# ---------------------------------------------------------------------------
# publishing
# ---------------------------------------------------------------------------

def publish(path: Path, payload: dict[str, Any]) -> bool:
    """Write the payload ATOMICALLY.  Returns success; never raises.

    mkstemp-then-``os.replace`` in the TARGET directory (the estate's
    ``vps_live_orchestrator.atomic_publish`` contract): the rename is atomic
    within a filesystem, so a reader gets the previous whole artifact or the new
    whole artifact and never a truncated one.  A pass that cannot write leaves
    the previous copy where it was — a stale-but-whole payload is self-describing
    through its own ``health.pass.at``, while a half-written one is a parse error.

    The directory is NEVER created when it is the VPS plane's; its absence means
    this host has no live plane.  A repo-local ``site/live`` IS created, because
    there the ladder's last rung is a path this checkout owns.
    """
    if no_publish():
        print(f"::warning title=entry-radar-live::{_NO_PUBLISH_ENV} is set — refusing "
              f"to write {path}", flush=True)
        return False
    parent = path.parent
    if not parent.is_dir():
        if parent == _VPS_LIVE_DIR:
            print(f"::notice title=entry-radar-live::{parent} is absent — no VPS live "
                  "plane on this host, so no served copy", flush=True)
            return False
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"::warning title=entry-radar-live::cannot create {parent} ({exc})",
                  flush=True)
            return False
    tmp_name: str | None = None
    try:
        body = json.dumps(payload, allow_nan=False, separators=(",", ":"),
                          default=str).encode("utf-8")
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o644)
        os.replace(tmp_name, path)
        tmp_name = None
        print(f"entry-radar-live published {path} ({len(body)} bytes)", flush=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=entry-radar-live::payload {path} not written ({exc}) — "
              "the previous copy stands", flush=True)
        return False
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# the pass
# ---------------------------------------------------------------------------

def _reader(state: Path | None):
    """The C3 minute reader, or None when this host cannot fetch minutes.

    Built lazily and tolerantly: C3 is one lane of several, and a host without a
    vendor key must still evaluate C1/C2 rather than stand the whole pass down.
    """
    try:
        from engine.entry_radar.vendor_minutes import VendorMinuteReader  # noqa: PLC0415
        return VendorMinuteReader(state_dir=state)
    except Exception as exc:  # noqa: BLE001
        print(f"::notice title=entry-radar-live::no C3 minute reader on this host "
              f"({exc}) — C1/C2 still evaluate, C3 publishes unavailable", flush=True)
        return None


def run(root: Path, *, now: datetime | None = None, dry_run: bool = False,
        state_override: str | None = None, live_override: str | None = None,
        spool_dir: str | None = None) -> int:
    """One pass, end to end.  Returns the process exit code."""
    try:
        LP.assert_published_spec_hashes()
    except LP.SpecHashDrift as exc:
        # BEFORE any write.  A level published under a hash that moved silently
        # re-attributes every result it later produces (§18 A5.0).
        print(f"::error title=entry-radar-live::{exc}", flush=True)
        return 2

    stamp = now or datetime.now(timezone.utc)
    state = state_dir(state_override)
    out_dir = live_dir(root, live_override)
    if spool_dir:
        os.environ["ENTRY_RADAR_SPOOL_DIR"] = str(spool_dir)

    pack: Any = None
    try:
        pack = LP.load_pack(state) if state is not None else None
        ledger = LL.LiveEpisodeLedger.load(state)
        quotes = load_quotes(root)
        spool = None if dry_run else LL.EventSpool()

        result = LE.run_pass(now=stamp, pack=pack, quotes=quotes, ledger=ledger,
                             state_dir=state, spool=spool,
                             intraday_reader=_reader(state),
                             unspooled_ok=dry_run, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 — the ``failed`` receipt's producer
        # NEVER SILENT, AND NEVER A STALE ARTIFACT LEFT STANDING.  A pass that
        # raised used to exit 0 with nothing written, so the served copy kept its
        # previous body AND its previous ``health.pass.at``: stale-but-whole, and
        # the only alarm was the session-grain freshness sentinel.  Publishing
        # the refusal receipt makes the failure legible in the artifact an
        # operator actually reads, and the nonzero exit makes it legible to the
        # unit.  Nothing is spooled and nothing is committed on this path.
        payload, health = LE.failure_payload(now=stamp, pack=pack, state_dir=state,
                                             error=exc)
        print(f"::error title=entry-radar-live::pass FAILED ({type(exc).__name__}: "
              f"{exc}) — publishing the failed receipt; zero transitions, zero spool",
              flush=True)
        log.warning("entry_radar_live: pass failed", exc_info=True)
        if not dry_run:
            publish(out_dir / PAYLOAD_NAME, payload)
        else:
            print(json.dumps({"health": health}, indent=2, default=str), flush=True)
        return 6

    health = result.health
    inputs = health.get("inputs", {})
    print(f"entry-radar-live pass={health['pass']['at']} state={health['state']} "
          f"pack={inputs.get('pack', {}).get('as_of')} "
          f"quotes={inputs.get('quotes', {}).get('coverage')}@"
          f"{inputs.get('quotes', {}).get('asof')} "
          f"src={quotes.get('source')}"
          f"{'(' + '+'.join(quotes['local_files']) + ')' if quotes.get('local_files') else ''} "
          f"transitions={len(result.payload.get('transitions') or [])} "
          f"events={len(result.payload.get('events') or [])} "
          f"basis={health.get('basis')} reasons={health.get('reasons')} "
          # Printed rather than merely declared, exactly as the sibling lanes
          # print theirs: an empty-by-design list nobody ever sees is a claim,
          # and a claim in a receipt is what makes the guard checkable.
          f"durable_writes={list(DURABLE_WRITES)}", flush=True)

    basis = health.get("basis") or {}
    if basis.get("mismatched_n"):
        print(f"::warning title=entry-radar-basis::{basis['mismatched_n']} probe name(s) "
              f"have a pack close that disagrees with the feed's previous close past "
              f"tolerance — those names are DARK (basis_mismatch), never re-based: "
              f"{', '.join(basis.get('refused') or [])}", flush=True)
    if not basis.get("audited_n") and basis.get("unchecked_n"):
        # A feed that stops publishing prevClose produces the same zero-mismatch
        # count as a healthy one.  Saying so is the whole point of the counter.
        print(f"::warning title=entry-radar-basis::none of {basis['unchecked_n']} probe "
              "name(s) carried a previous close — the levels-vs-tape basis is "
              "UNVERIFIED this pass, not verified clean", flush=True)
    if health["state"] in LE.CYCLE_REFUSALS:
        print(f"::warning title=entry-radar-live::whole-cycle refusal "
              f"({health['state']}: {'; '.join(health.get('reasons') or [])}) — every "
              "probe name unavailable, zero transitions, zero spool", flush=True)
    gap = (health.get("pass") or {}).get("prev_gap_intervals")
    if gap:
        print(f"::warning title=entry-radar-live::cadence gap — {gap} interval(s) "
              "missed since the previous pass", flush=True)
    if not result.committed:
        print("::warning title=entry-radar-live::event spool failed — this pass's "
              "transitions are withheld from the ledger AND the payload; the next "
              "pass re-derives and retries", flush=True)

    if dry_run:
        print(json.dumps({"health": health,
                          "transitions": result.payload.get("transitions"),
                          "events": result.payload.get("events")},
                         indent=2, default=str), flush=True)
        return 0

    ledger.save()
    published = publish(out_dir / PAYLOAD_NAME, result.payload)
    if not published:
        # A DOCUMENTED REHEARSAL IS NOT A FAILURE.  ``ENTRY_RADAR_NO_PUBLISH`` is
        # the switch that makes ``publish`` refuse on purpose (script docstring),
        # so returning 3 there reddened every rehearsal pass with the code that
        # means "the sink is broken" — and a code that fires on purpose stops
        # meaning anything when it fires for real.
        return 0 if no_publish() else 3
    return result.exit_code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Live Entry Radar — the 5-minute RTH evaluator pass.")
    ap.add_argument("--root", default=str(ROOT), help="repo root (default: this checkout)")
    ap.add_argument("--state-dir", default=None,
                    help="runtime state plane (default: $ENTRY_RADAR_STATE_DIR → VPS)")
    ap.add_argument("--live-dir", default=None,
                    help="live-artifact directory (default: the §7.3 ladder)")
    ap.add_argument("--spool-dir", default=None,
                    help="local spool directory (sets $ENTRY_RADAR_SPOOL_DIR)")
    ap.add_argument("--now", default=None,
                    help="ISO instant override for the pass clock (tests / replays)")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run",
                    help="evaluate and print; spool nothing, commit nothing, publish nothing")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        stream=sys.stderr)
    root = Path(args.root)
    now: datetime | None = None
    if args.now:
        try:
            parsed = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        except ValueError:
            print(f"::error title=entry-radar-live::unparseable --now {args.now!r}",
                  flush=True)
            return 2
        now = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    lock = _lock_path(args.state_dir)
    handle = None
    if lock is not None:
        try:
            lock.parent.mkdir(parents=True, exist_ok=True)
            handle = lock.open("a+")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # A held lock means the previous pass is still deriving.  Skipping is
            # correct and cheap: the next tick is five minutes away, and two
            # passes over the same journal would both spool the same transitions.
            if handle is not None:
                handle.close()
            print("::notice title=entry-radar-live::a pass is already running "
                  "(lock held) — standing down", flush=True)
            return 0
    try:
        return run(root, now=now, dry_run=bool(args.dry_run),
                   state_override=args.state_dir, live_override=args.live_dir,
                   spool_dir=args.spool_dir)
    except Exception as exc:  # noqa: BLE001
        # The LAST-RESORT handler.  ``run`` publishes the ``failed`` receipt for
        # anything raised inside the pass, so reaching here means the failure was
        # in the wiring around it (or in the receipt path itself) and there is no
        # resolved live directory to publish into.  Nonzero either way: exiting 0
        # on an unexplained failure is how a lane burns a session looking green.
        print(f"::error title=entry-radar-live::pass failed before any receipt could "
              f"be written: {exc}", flush=True)
        log.warning("entry_radar_live: unexpected failure", exc_info=True)
        return 6
    finally:
        if handle is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()


def _lock_path(override: str | None) -> Path | None:
    state = state_dir(override)
    return None if state is None else state.parent / LOCK_NAME


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
