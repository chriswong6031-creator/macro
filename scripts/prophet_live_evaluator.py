"""scripts/prophet_live_evaluator.py — the 5-minute Prophet Live intraday pass (P0 D3).

Loads tonight's armed pack from R2, reads the freshest delayed quote view, runs the
state machine in :mod:`engine.prophet_live.live_states`, and publishes the full state
map plus, when anything actually moved, an object-per-pass event spool row set.

    python -m scripts.prophet_live_evaluator [--dry-run] [--now ISO] [--root PATH]

WHERE IT RUNS (masterplan §4.2a, ruled 2026-07-30). The VPS systemd timer
``macro-live-prophet.timer`` is the product lane; ``.github/workflows/prophet-live.yml``
is a self-disabling backstop. GitHub's scheduler throttles this repo's frequent crons
far past the documented 15-45 min (measured: a ``*/5`` lane ran 09:07Z then 12:19Z),
so a 5-minute product cadence is not purchasable there at any price. The CODE is the
same on both hosts — same states, same gates, same artifact — only the host and the
quote source move.

QUOTE SOURCE, IN PREFERENCE ORDER (§4.2a fact 2).
  1. THE VPS LOCAL PLANE (``local_quote_paths``): files the systemd lanes publish by
     atomic rename on this same box — no network, no auth, no rate limit, seconds old.
  2. THE ESTATE MERGE (:func:`engine.marketing.live_verify.load_live_quotes`), which
     reads the repo checkout. On a GitHub runner that is the only source there is.
The fall-back is unconditional and silent for an absent plane: a host without
``/var/lib/macro-live`` is not broken, it is simply not the VPS. What the local plane
must never do is degrade a pass — a missing, unreadable or empty local file falls
through to the merge rather than raising or blanking the tape.

LEDGER LAW (G0.2). This lane writes NOTHING under ``data/`` and commits nothing. It
runs 80+ times a session; the nightly reconciler is the sole writer of
``data/prophet_live/``, and the nightly build remains the only thing that confirms,
grades or advances a ledger. The workflow has no write permission and no git step.
The ONE filesystem write on this path is the served copy (``served_path``), which goes
to the VPS live plane — outside the git work-tree, outside ``site.served``, and never
under ``data/``.

QUOTE AGE = FEED DELAY + POLLING GAP. Per-quote age is measured from the quote's own
timestamp, so it carries the vendor's contractual delay (~15 min for US single names)
before this lane has done anything at all. ``quote_max_age_min`` is therefore DERIVED —
``live.delayed_min + prophet_live.quote_slack_min`` — and only the slack half is about
our cadence (see :func:`engine.prophet_live.live_states.live_cfg`). Do not "tighten" it
back toward 12: that number cannot be met by a delayed feed at any polling speed, and
the resulting all-dark artifact looks exactly like a healthy lane.

HONEST DEGRADATION (G0.3). Three independent ways to be dark, all named:
  * pack missing            → whole artifact ``status:"dark" reason:"no_pack"``
  * pack ``as_of`` is not the last completed session → ``"stale_pack"``; yesterday's
    triggers are never evaluated against today's tape
  * per-name: no quote, quote older than ``quote_max_age_min``, an irregular gate,
    a name the pack could not probe, or a pack close that disagrees with the feed's
    previous close past ``basis_tolerance_pct`` (``basis_mismatch``, W-L0 gate 3) →
    that NAME goes dark with its reason while the rest of the artifact stays live.
No path invents a state, and nothing here says fired, confirmed or refuted.

ONE PRICE BASIS (W-L0 gate 3). The armed levels are adjusted store closes; the tape is
raw vendor prints. Both are NAMED on every payload (``meta.price_adjustment``) and the
per-pass assertion that they still describe the same scale — pack ``as_of_close`` vs
feed ``prev_close``, per name — is ``live_states.evaluate``'s first act. This script
owns only the LOUD half: the aggregate line, a ``::warning`` when names actually
mismatch, and a second one when NOTHING could be checked, because a feed that stops
publishing ``prevClose`` produces the same zero-mismatch count as a healthy one.

NO PANDAS ON THIS PATH. The workflow installs ``pyyaml boto3`` only.
``live_verify`` imports pandas lazily (inside its earnings helper, which this lane
never calls) and ``live_states``/``r2io`` are stdlib plus a lazy boto3, so the whole
import closure is thin by construction.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _CODE_ROOT)

from engine.marketing import live_verify as LV  # noqa: E402
from engine.prophet_live import live_states as LS  # noqa: E402
from engine.prophet_live import r2io  # noqa: E402

log = logging.getLogger("prophet_live_evaluator")

#: ``meta.quote_source`` when the pass read the box's own live plane. One token, not a
#: path: the artifact is served to entitled sessions, and a server path in a payload is
#: noise at best. The resolved filenames go to the journal line instead.
LOCAL_SOURCE = "vps_local"

#: The VPS live plane, preference order, both published by atomic rename by
#: ``scripts/vps_live_orchestrator.py`` (docs/VPS_LIVE_ORCHESTRATION.md §Runtime layout).
#:
#: A LIST OF TWO, RATIFIED 2026-07-30 — do NOT "simplify" it back to the single served
#: ``live/quotes.json``. The spec said "read the local plane"; read literally as the
#: served file alone it evaluates ~0 of ~1,700 armed names, because that file is the
#: 34-symbol DISPLAY set (measured, see below). Both files, merged freshest-wins.
#:
#: BOTH, not just the served one, and the order is load-bearing:
#:   quotes_full.json  the ~2,100-symbol universe the 5-minute ``snapshot`` lane pulls
#:                     (state dir, root-readable, not web-addressable). This is the
#:                     coverage source — it is the local twin of the ``live-data``
#:                     branch snapshot the merge path fetches.
#:   live/quotes.json  the ~34-symbol DISPLAY set the 60-second ``fast`` lane pulls.
#:                     Measured 2026-07-30: 34 symbols, index/ETF/macro only. Reading
#:                     this one ALONE would evaluate ~0 of the ~1,700 armed names and
#:                     dark the rest ``no_quote`` — fresher, and empty.
#: They are merged freshest-wins through live_verify's own ``_merge_quotes``, so "which
#: quote is newer" has exactly one definition in the estate.
LOCAL_QUOTE_PATHS: tuple[str, ...] = (
    "/var/lib/macro-live/state/quotes_full.json",
    "/var/lib/macro-live/public/live/quotes.json",
)

#: Where the served copy lands (§4.4a, CHOSEN option). Same-origin, behind Caddy's
#: ``@reg_asset`` default-deny route — ``prophet_live.json`` is deliberately NOT one of
#: the ``quotes.json``/``breadth.json`` public exceptions. The payload is per-name
#: STATES (the armed LEVELS stay in the R2 pack and are never served), but naming which
#: tickers are armed and which are forming today is pre-publication board membership,
#: and #3391 — the ruling that regwalled ``/factordata/*`` — is exactly about that.
#:
#: THE PREFIX IS BRIDGED HERE, ON PURPOSE. The R2 key is ``live_flow/prophet_live.json``
#: (``r2io.LIVE_KEY``); the page fetches ``live/prophet_live.json``. Do not "fix" the
#: mismatch by renaming the R2 key (the reconciler and the spool prefix key off it) and
#: do not move the served path (the P1 consumer is tested against it).
SERVED_PATH = "/var/lib/macro-live/public/live/prophet_live.json"


def cfg_block(conf: dict[str, Any] | None) -> dict[str, Any]:
    """The ``prophet_live`` block of config.yml as a plain dict (never raises).

    Read straight off the raw config rather than through ``live_states.live_cfg``:
    the state machine's resolver owns the keys that change STATE SEMANTICS and its
    defaults table is that contract. Host wiring — where the quotes are, where the
    served copy goes — is this script's business and must not widen that surface.
    """
    if not isinstance(conf, dict):
        return {}
    block = conf.get("prophet_live")
    return block if isinstance(block, dict) else {}


def local_quote_paths(block: dict[str, Any]) -> list[Path]:
    """Configured local quote files, defaulting to :data:`LOCAL_QUOTE_PATHS`.

    An explicit empty list in config.yml disables the local plane entirely (the merge
    path, exactly as before) — that is the config-only rollback, no code change.
    """
    raw = block.get("local_quote_paths", None)
    if raw is None:
        raw = list(LOCAL_QUOTE_PATHS)
    if isinstance(raw, (str, Path)):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        print("::warning title=prophet-live::prophet_live.local_quote_paths is not a "
              "list — using the built-in VPS live plane paths", flush=True)
        raw = list(LOCAL_QUOTE_PATHS)
    return [Path(str(p)) for p in raw if str(p).strip()]


def served_path(block: dict[str, Any]) -> Path | None:
    """Where to write the served copy, or None when it is switched off ("" in config)."""
    raw = block.get("served_path", SERVED_PATH)
    text = str(raw or "").strip()
    return Path(text) if text else None


def _read_local_json(path: Path) -> dict | None:
    """One local quote file, or None. A corrupt file WARNS; an absent one does not.

    The distinction is the whole point: no file means this host has no live plane
    (every GitHub runner, every dev checkout), which is normal. A file that exists and
    will not parse means the plane is there and broken, which is not.
    """
    try:
        if not path.is_file():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=prophet-live::local quote file {path} unreadable "
              f"({exc}) — falling back to the merged quote view", flush=True)
        return None


def load_local_quotes(block: dict[str, Any]) -> dict[str, Any] | None:
    """The local plane in ``load_live_quotes`` shape, or None when it has nothing.

    Deliberately built on live_verify's own private helpers (``_quotes_from_snapshot``,
    ``_merge_quotes``, ``_artifact_ms``, ``_feed_delay_min``) rather than a second
    reader: the shape of a quote artifact, which quote wins a tie, and what a feed's
    declared delay means are estate-wide definitions, and a private copy of them here
    is how two surfaces end up disagreeing about the same tape.

    Returns None — not an empty view — when nothing readable carries a quote, so the
    caller falls back instead of publishing a tape-wide ``no_quote``.
    """
    quotes: dict[str, dict] = {}
    asof: str | None = None
    asof_ms: float | None = None
    used: list[str] = []
    feed_delay = 0.0
    for path in local_quote_paths(block):
        obj = _read_local_json(path)
        if not obj:
            continue
        q = LV._quotes_from_snapshot(obj)  # noqa: SLF001
        if not q:
            continue
        obj_ms = LV._artifact_ms(obj)  # noqa: SLF001
        LV._merge_quotes(quotes, q, obj_ms)  # noqa: SLF001
        used.append(path.name)
        feed_delay = max(feed_delay, LV._feed_delay_min(obj))  # noqa: SLF001
        # The NEWEST artifact's asof, not the last one read: it is the fallback age for
        # every quote with no ts of its own (same rule load_live_quotes applies).
        if obj_ms is not None and (asof_ms is None or obj_ms > asof_ms):
            asof, asof_ms = obj.get("asof"), obj_ms
        elif asof is None:
            asof = obj.get("asof") or asof
    if not quotes:
        return None
    return {"quotes": quotes, "asof": asof, "source": LOCAL_SOURCE,
            "feed_delay_min": feed_delay, "local_files": used}


def load_quotes(root: Path, block: dict[str, Any]) -> dict[str, Any]:
    """The local plane if it has anything, else the estate merge — exactly as before."""
    local = load_local_quotes(block)
    if local is not None:
        return local
    return LV.load_live_quotes(root)


def publish_served(path: Path, payload: dict[str, Any]) -> bool:
    """Write the served copy ATOMICALLY. Returns success; never raises.

    Temp-file-then-rename in the TARGET directory (the estate's
    ``vps_live_orchestrator.atomic_publish`` contract): ``os.replace`` is atomic within
    a filesystem, so Caddy either serves the previous whole artifact or the new whole
    artifact and never a truncated one. A pass that cannot write leaves the previous
    copy exactly where it was — a stale-but-whole payload is self-describing through its
    own ``meta.pass_ts``, while a half-written one is a parse error on a live page.

    The directory is NEVER created. Its absence means this host has no live plane, and
    a lane that mkdir'd one would leave Caddy a directory to serve nothing out of.

    ``PROPHET_LIVE_NO_PUBLISH`` refuses this write too, exactly as it refuses every R2
    PUT (``r2io.put_json``). It would be perverse for the kill switch that exists to
    keep a rehearsal out of the EVIDENCE to leave the USER-FACING copy writable — and
    on the VPS it is also the only stand-down that needs no unit change: set it in
    /etc/macro-live.env and the timer keeps ticking while nothing is published anywhere.
    """
    if os.environ.get("PROPHET_LIVE_NO_PUBLISH", "").strip() not in ("", "0", "false"):
        print("::warning title=prophet-live::PROPHET_LIVE_NO_PUBLISH is set — refusing "
              f"to write {path}", flush=True)
        return False
    parent = path.parent
    if not parent.is_dir():
        print(f"::notice title=prophet-live::{parent} is absent — no VPS live plane on "
              "this host, so no served copy (R2 is unaffected)", flush=True)
        return False
    tmp_name: str | None = None
    try:
        # Serialise BEFORE creating the temp file: a payload that will not encode must
        # not leave a stray dot-file next to a live artifact.
        body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
            os.fchmod(fh.fileno(), 0o644)
        os.replace(tmp_name, path)
        tmp_name = None
        print(f"prophet-live served {path} ({len(body)} bytes)", flush=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=prophet-live::served copy {path} not written ({exc}) — "
              "the previous copy stands", flush=True)
        return False
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def load_config(root: Path) -> dict[str, Any]:
    """config.yml as a plain dict. Never raises — defaults cover an unreadable file."""
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load((root / "config.yml").read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=prophet-live::config.yml unreadable ({exc}) "
              "— in-code defaults", flush=True)
        return {}


def quote_ager(live: dict[str, Any], now: datetime):
    """A ``quote -> age in minutes`` callable built on live_verify's own staleness math.

    Deliberately the private ``LV._quote_age_min``: quote age is the number this
    lane's whole freshness gate turns on, and a second copy of "own ts_ms, else the
    artifact asof" is how two surfaces end up disagreeing about what stale means.
    """
    asof = live.get("asof")
    return lambda q: LV._quote_age_min(q, asof, now)  # noqa: SLF001


def no_publish_set() -> bool:
    """True when the operator kill switch is engaged (an INTENTIONAL stand-down)."""
    return os.environ.get("PROPHET_LIVE_NO_PUBLISH", "").strip() not in ("", "0", "false")


def publication_required(dry_run: bool, explicit: bool | None = None) -> bool:
    """Whether THIS pass owes the world a publication.

    Fail-closed by construction: any real pass owes a publication unless something
    EXPLICIT says otherwise. Before the 2026-08 incident the contract was inverted
    -- publication was best-effort, every failure was a warning, and the process
    exited 0 -- so a lane that had never once published looked healthy for 27 days.

    The opt-outs are explicit MODES, never host-name guessing (a runner and the VPS
    are told apart by what they own, not by what they are called):
      * ``--dry-run``                     evaluate and print; nothing is owed
      * ``--no-require-publish`` / env 0  dev/CI running the real path deliberately
      * ``PROPHET_LIVE_NO_PUBLISH``       operator kill switch; the stand-down is
                                          intentional, so it is not a fault -- but it
                                          is also never reported as a healthy publish
    """
    if dry_run or no_publish_set():
        return False
    if explicit is not None:
        return explicit
    raw = os.environ.get("PROPHET_LIVE_REQUIRE_PUBLISH", "").strip().lower()
    if raw in ("0", "false", "no"):
        return False
    return True


def run(root: Path, *, now: datetime | None = None, dry_run: bool = False,
        cfg: dict[str, Any] | None = None, require_publish: bool | None = None) -> int:
    """One evaluator pass.

    Exit codes are a CONTRACT (2026-08 silent-freeze repair):
      0  nothing was owed, or everything owed was published
      3  a REQUIRED publication was impossible or failed -- the lane is not producing
      1  unexpected failure (raised by ``main``)
    """
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    conf = cfg if cfg is not None else load_config(root)
    lc = LS.live_cfg(conf)
    block = cfg_block(conf)

    if not LS.in_window(ts, lc):
        w = lc.get("window_et") or {}
        print(f"::notice title=prophet-live::outside the {w.get('start')}-{w.get('end')} "
              f"ET weekday window ({ts.strftime('%Y-%m-%dT%H:%MZ')}) — standing down",
              flush=True)
        return 0

    owes_publication = publication_required(dry_run, require_publish)
    s3 = r2io.client()
    if s3 is None:
        # Line-start ::error, not ::warning, when a publication is owed. This exact
        # line printed ~1,500 times between 2026-07-30 and 2026-08-26 while the pass
        # returned 0 -- the credentials were never seeded at cutover and nothing
        # anywhere turned that into a failure.
        level = "error" if owes_publication else "warning"
        print(f"::{level} title=prophet-live::no R2 credentials — reading the public "
              "mirror, publishing nothing this pass", flush=True)

    pack = r2io.get_json(r2io.PACK_KEY, s3=s3)
    prev = r2io.get_json(r2io.LIVE_KEY, s3=s3, allow_public=False)

    live = load_quotes(root, block)
    quotes = live.get("quotes") if isinstance(live.get("quotes"), dict) else {}
    delay_min = None
    try:
        delay_min = int(((conf.get("live") or {}).get("delayed_min")))
    except (TypeError, ValueError):
        delay_min = None

    # THE CEILING MUST CLEAR THE FLOOR. A quote's age is (how long since we looked)
    # PLUS (how far behind real-time the tape is) — live_verify._feed_delay_min states
    # the rule — and the per-name gate measures the sum. A ceiling at or below the feed's
    # own declared delay is unsatisfiable by construction: every US single name darks
    # `stale_quote` on every pass, on the freshest plane there is, while the lane reports
    # success. live_cfg now DERIVES the ceiling from that floor, so this can no longer
    # be true of the default — it guards an explicit `quote_max_age_min` override and the
    # case where the ARTIFACT declares a longer delay than config.yml admits, which no
    # derivation from config can see.
    try:
        ceiling = float(lc.get("quote_max_age_min", LS._FALLBACK_MAX_AGE_MIN))  # noqa: SLF001
        floor = max(float(live.get("feed_delay_min") or 0.0), float(delay_min or 0))
        if floor and ceiling <= floor:
            print(f"::warning title=prophet-live::quote_max_age_min={ceiling:g}m is at "
                  f"or below the feed's declared {floor:g}m delay — names cannot pass "
                  "the per-quote freshness gate at any polling speed (unset "
                  "prophet_live.quote_max_age_min to derive it, or raise "
                  "prophet_live.quote_slack_min)", flush=True)
    except (TypeError, ValueError):
        pass

    art = LS.evaluate(pack, quotes, prev, now=ts, cfg=lc,
                      quote_asof=live.get("asof"), delay_min=delay_min,
                      quote_age_of=quote_ager(live, ts))
    art["meta"]["quote_source"] = live.get("source")

    m = art["meta"]
    if art["status"] == "dark":
        print(f"::warning title=prophet-live::artifact dark ({art['reason']}) — "
              f"{m.get('detail') or 'no evaluable pack'}", flush=True)
    else:
        # Coverage, stated every pass: what the pack could not arm is not "dormant".
        # ONE definition of "unprobed" — live_states counts pack entries with
        # probed=False while walking them, so recomputing universe_n - probed_n here
        # would put two numbers with different edge cases in the same payload.
        pm = (pack or {}).get("meta") or {}
        m["coverage"] = {"pack_universe_n": pm.get("universe_n"),
                         "pack_probed_n": pm.get("probed_n"),
                         "pack_armed_n": pm.get("armed_n"),
                         "pack_edges_checked": pm.get("edges_checked"),
                         "unprobed_n": m.get("unprobed_n"),
                         "pack_skipped": pm.get("skipped")}
        # ONE PRICE BASIS (W-L0 gate 3). The per-name verdict is already in the
        # artifact — every mismatch is a `basis_mismatch` dark row — so this is the
        # AGGREGATE, which is the thing a per-name dark cannot say: a handful of names
        # is a dividend calendar, most of the tape is a basis-wide break (a re-based
        # store, a vendor switch on the quote plane), and only the second one is an
        # incident. `unchecked_n` is reported in the same breath because a feed that
        # stops carrying `prevClose` produces zero mismatches and zero assurance, and
        # those two must never read the same.
        ba = m.get("price_adjustment") or {}
        checked, unchecked = int(ba.get("checked_n") or 0), int(ba.get("unchecked_n") or 0)
        bad = ba.get("mismatched") or {}
        print(f"prophet-live basis levels={ba.get('levels')} quote={ba.get('quote')} "
              f"checked={checked} unchecked={unchecked} mismatched={len(bad)} "
              f"tol={ba.get('tol_pct')}%", flush=True)
        if bad:
            worst = sorted(bad.items(), key=lambda kv: -abs(float(kv[1])))[:6]
            share = (len(bad) / checked * 100.0) if checked else 0.0
            print(f"::warning title=prophet-live-basis::{len(bad)} of {checked} names "
                  f"({share:.1f}%) have a pack close that disagrees with the feed's "
                  f"previous close by more than {ba.get('tol_pct')}% — those names are "
                  f"dark (basis_mismatch), not re-based: "
                  f"{', '.join(f'{t} {g:+.2f}%' for t, g in worst)}", flush=True)
        if checked == 0 and unchecked:
            print(f"::warning title=prophet-live-basis::none of {unchecked} armed names "
                  "carried a previous close to check the price basis against — the "
                  "levels-vs-tape basis is UNVERIFIED this pass, not verified clean",
                  flush=True)
        print(f"prophet-live pass={m['pass_ts']} pack_as_of={m['pack_as_of']} "
              f"quotes={m['quotes_n']}@{m['quote_asof']} src={live.get('source')}"
              f"{'(' + '+'.join(live['local_files']) + ')' if live.get('local_files') else ''} "
              f"states={m['states']} dark={m['dark_counts']} "
              # The pack's coverage limit, printed beside the lane's. They are two
              # different failures and a single "unreadable" number hides that.
              f"unknown={m.get('unknown_counts')} events={m['events_n']}",
              flush=True)
        for ev in art.get("events") or []:
            print(f"prophet-live EVENT {ev['kind']} {ev['ticker']} px={ev.get('price')} "
                  f"from={ev.get('from')} passes={ev.get('passes')} "
                  f"age={ev.get('quote_age_min')}m", flush=True)
        if m["dark_counts"].get("stale_quote") or m["dark_counts"].get("no_quote"):
            print(f"::warning title=prophet-live::{m['dark_counts'].get('no_quote', 0)} "
                  f"names without a quote and "
                  f"{m['dark_counts'].get('stale_quote', 0)} past the "
                  f"{lc['quote_max_age_min']}m freshness gate — those names are dark, "
                  "not guessed", flush=True)

    events = art.pop("events", [])
    if dry_run:
        print(json.dumps({"artifact_meta": art["meta"], "events": events}, indent=2,
                         default=str), flush=True)
        return 0

    published: list[str] = []
    unpublished: list[str] = []

    if s3 is None:
        # No served copy either, deliberately. Without credentials there is no `prev`
        # (the debounce predecessor is read authenticated, never off the CDN), so every
        # pass would restart its counters: crosses could never bank their second pass
        # and `since_ts` would re-stamp on every tick. Publishing that to a page would
        # be a worse lie than publishing nothing. Operator step, named in the PR: put
        # R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET in
        # /etc/macro-live.env (0600) and make sure boto3 is in /opt/macro/.venv.
        if owes_publication:
            print("::error title=prophet-live::publication was required and no R2 "
                  "client could be built — nothing was published this pass", flush=True)
            return 3
        return 0
    ok = r2io.put_json(r2io.LIVE_KEY, art, s3=s3)
    if ok:
        published.append(r2io.LIVE_KEY)
    else:
        unpublished.append(r2io.LIVE_KEY)
        print(f"::{'error' if owes_publication else 'warning'} title=prophet-live::"
              "live artifact PUT failed — the next pass loses its debounce history",
              flush=True)

    # The served copy (§4.4a). Independent of the R2 result on purpose: R2 is the
    # PIPELINE artifact the nightly reconciler reads, the served file is the PRODUCT
    # path, and one plane hiccuping must not stale the other. Same payload object as
    # the PUT above, so the two planes can never describe different tapes.
    served = served_path(block)
    if served is not None:
        # Owning a live plane is a CAPABILITY, not a hostname: the directory is
        # never created, so its absence means this host serves nothing and owes
        # nothing. A CI runner therefore cannot be failed for a directory it does
        # not own, while the VPS -- which does own it -- cannot fail silently.
        host_serves = served.parent.is_dir()
        if publish_served(served, art):
            published.append(str(served))
        elif host_serves:
            unpublished.append(str(served))
            print(f"::{'error' if owes_publication else 'warning'} title=prophet-live::"
                  f"served copy {served} could not be written", flush=True)

    if events:
        stamp = LS.et_clock(ts).strftime("%H%M%S")
        key = r2io.events_key(m["session_et"], stamp)
        spool = {"schema": "prophet_live.events/v1", "pass_ts": m["pass_ts"],
                 "session_et": m["session_et"], "pack_as_of": m.get("pack_as_of"),
                 "quote_asof": m.get("quote_asof"), "events": events}
        if r2io.put_json(key, spool, s3=s3):
            published.append(key)
        else:
            unpublished.append(key)
            print(f"::{'error' if owes_publication else 'warning'} title=prophet-live::"
                  f"event spool PUT {key} failed — {len(events)} transitions are not "
                  "in tonight's evidence", flush=True)

    # PARTIAL EFFECT IS REPORTED, NEVER RETRIED HERE. Naming exactly which objects
    # landed and which did not is what lets the next actor reconcile instead of
    # guessing; a blind retry through another carrier is how one logical
    # publication becomes two conflicting ones.
    if unpublished:
        print(f"prophet-live publication partial: landed={len(published)} "
              f"failed={len(unpublished)} [{', '.join(unpublished)}]", flush=True)
        if owes_publication:
            return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prophet Live intraday evaluator — provisional states off the armed pack.")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="evaluate and print; write nothing to R2")
    parser.add_argument("--now", default=None,
                        help="ISO timestamp override for the pass clock (tests / replays)")
    parser.add_argument("--root", default=None, help="repo root (default: this script's parent)")
    publish = parser.add_mutually_exclusive_group()
    publish.add_argument("--require-publish", dest="require_publish", action="store_true",
                         default=None,
                         help="fail (exit 3) when a required publication cannot happen")
    publish.add_argument("--no-require-publish", dest="require_publish",
                         action="store_false",
                         help="dev/CI: run the real path without owing a publication")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        stream=sys.stderr)
    root = Path(args.root) if args.root else Path(_CODE_ROOT)
    now: datetime | None = None
    if args.now:
        try:
            now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        except ValueError:
            print(f"::error title=prophet-live::unparseable --now {args.now!r}", flush=True)
            return 2
    try:
        return run(root, now=now, dry_run=bool(args.dry_run),
                   require_publish=args.require_publish)
    except Exception as exc:  # noqa: BLE001
        # This used to return 0 -- justified as "a lane that turns 80 runs a day red
        # is noise". On a systemd product lane fronted by an external dead-man it
        # produced the opposite failure: a dead producer that looks successful
        # forever. Noise is a threshold problem; a swallowed exception is a
        # blindness problem, and only one of the two can hide a 27-day outage.
        print(f"::error title=prophet-live::pass failed: {exc}", flush=True)
        log.warning("prophet_live_evaluator: unexpected failure", exc_info=True)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
