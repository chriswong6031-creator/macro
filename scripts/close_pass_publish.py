"""scripts.close_pass_publish — the evening close-pass lane (W-L1a).

Recomputes tonight's ADMISSION plus the close-derived score legs from the day's
closes and publishes the provisional board to the RUNTIME plane: an R2 object,
mirrored to the VPS live plane by macro-live-closepass. The nightly remains the
sole writer of record.

LEDGER LAW (G0.2, DNR:KILL-INTRADAY-CHRONICLE). This lane writes no ``data/``
path, advances no forward ledger, touches nothing under ``data/prophet_live/``,
and runs no git command. Its only filesystem write is the configured served
path, by temp-file-then-rename. ``tests/test_close_pass_lane.py`` pins all of
that by AST rather than by intention, in the shape
``tests/test_prophet_live_vps_lane.py`` established.

OFF THE RENDER CRITICAL PATH — deliberately. closing-bell.yml already ships a
full provisional site at 16:05 ET, but it takes a measured 109 minutes behind an
81-minute spine and lands ~17:55 ET against an 18:30 SLA. Adding the board to
that lane would spend the entire 35-minute margin. This publishes to the live
plane instead, so it lands ~30 minutes after the close no matter what the spine
is doing, and a slow render can never make the board late.

WHY THIS IS NOT A SECOND OPINION. Every board published here is graded against
the nightly board of record the same night (``scripts.close_pass_reconcile``),
per name, and the delta is published. See ``engine.close_pass.reconcile``.

Usage:
  python -m scripts.close_pass_publish              # one pass
  python -m scripts.close_pass_publish --dry-run    # compute, publish nothing
  python -m scripts.close_pass_publish --now 2026-08-09T20:20:00Z
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.close_pass import board as CB  # noqa: E402
from engine.close_pass import massive_close as MC  # noqa: E402
from engine.prophet_live import r2io  # noqa: E402

#: The R2 key the VPS mirror pulls. Same ``live_flow/`` prefix as the rest of
#: the runtime plane, so one bucket policy covers all of it.
BOARD_KEY = "live_flow/us_board_provisional.json"
#: Where the VPS serves it from. NOT public: /live/ is default-deny at the Caddy
#: boundary and this artifact is deliberately not one of the reviewed
#: exceptions — the real board is not free content (#3391).
SERVED_PATH = "/var/lib/macro-live/public/live/us_board_provisional.json"
#: The stand-down. Its own switch rather than PROPHET_LIVE_NO_PUBLISH: sharing
#: one would mean a Prophet Live rehearsal silently darks the evening board too.
NO_PUBLISH_ENV = "CLOSE_PASS_NO_PUBLISH"

_TAG = "close-pass"


def _warn(msg: str) -> None:
    """A GitHub annotation must START the line, so it is printed bare.

    Through a logger it would emit ``WARNING ::warning …`` and GitHub silently
    drops it: the call reviews as an alarm, runs clean and produces nothing.
    ``flush`` is load-bearing — stdout is block-buffered when piped in CI.
    """
    print(f"::warning title={_TAG}::{msg}", flush=True)


def _notice(msg: str) -> None:
    print(f"::notice title={_TAG}::{msg}", flush=True)


def session_date(now: datetime) -> str | None:
    """The ET session this pass describes, or None on a non-session day.

    ``is_session`` on the ET date, NOT ``expected_last_session()`` — the same
    adaptation closing-bell.yml documents: this lane fires before the 17:00 ET
    settle buffer, so ``expected_last_session`` still resolves to YESTERDAY and
    would stamp every evening board with the previous session's date.
    """
    from lib.nyse_calendar import ET, is_session
    et = now.astimezone(ET).date()
    return et.isoformat() if is_session(et) else None


def _with_session_close(close: Any, session: str, price: float) -> Any:
    """One close series + today's close → the same series with today's bar.

    IN MEMORY AND NOWHERE ELSE (G0.2). This appends a row to a pandas object the
    pass is holding; nothing is written back to the store, which is the nightly's
    to advance. The returned object is a new Series — the store's own frame is
    never mutated, so a caller that re-reads the same ticker sees the store.

    The stamp is built on the EXISTING index's timezone rather than a naive
    ``Timestamp``: a tz-aware store index concatenated with a naive stamp yields
    an object-dtype index, and every downstream ``.date()`` and comparison then
    works on the wrong type instead of raising where it could be seen.
    """
    import pandas as pd  # noqa: PLC0415

    tz = getattr(getattr(close, "index", None), "tz", None)
    stamp = pd.Timestamp(session)
    if tz is not None:
        stamp = stamp.tz_localize(tz)
    return pd.concat([close, pd.Series([float(price)], index=[stamp],
                                       name=getattr(close, "name", None))])


def collect(session: str) -> dict[str, Any]:
    """Read the price store and run the gate. The only heavy step in the lane.

    Split out so the transport, the guards and the payload shape are all
    testable without a 2 GB parquet store — and so the one function that
    touches the store is the one place a reviewer has to look for I/O.

    Imports are function-scoped: ``build_stock_library`` is a 5,900-line module
    whose import cost belongs to the pass that needs it, not to ``--help``.
    """
    from engine import signal_gate  # noqa: PLC0415
    from engine.extension import extension_signals  # noqa: PLC0415
    from engine.i18n import tr  # noqa: PLC0415
    from lib import delisted_symbols  # noqa: PLC0415
    from scripts.build_stock_library import (  # noqa: PLC0415
        extension_panels, universe, universe_price_adjustment,
    )
    import pandas as pd  # noqa: PLC0415

    uni = universe()
    adjustment_by = universe_price_adjustment()

    # ── SAME-DAY CLOSE TRUTH ─────────────────────────────────────────────────
    # MEASURED: the Fri 2026-08-14 pass evaluated 253 of a 1,763-name universe —
    # `skipped {'no_todays_bar': 1508}`, 86% of the market — because the lane's
    # keyless Yahoo heal refreshes the index group and the deep per-name stores
    # are the nightly's to advance. Massive's grouped daily is ONE request for
    # the whole market, so the coverage hole closes without a per-name fetch.
    #
    # THE BASIS LAW, and it is the whole reason this splice is legal.
    # A store history is re-based RETROSPECTIVELY at each ex-date: the vendor
    # divides every PRIOR bar by the split/dividend factor and leaves the newest
    # bar alone. So for any name with NO same-session corporate action, today's
    # raw close IS today's adjusted close — the same number, exactly, on both
    # `universe_price_adjustment()` families (ADJUSTED per-name stores and the
    # UNADJUSTED breadth caches alike). The append is therefore exact, not
    # approximate, and no per-name `price_basis` changes.
    # For a name WITH a same-session action the two numbers differ by the factor
    # itself — BYND reverse-split 1:30 on 2026-08-14, so its raw close that day
    # sits 30× off its own pre-split history, a fabricated gap the gate would
    # happily score. Such a name is DARKED, never spliced; the nightly settles it
    # hours later. Measured for 2026-08-14: 3 splits and 450 ex-dividends
    # market-wide, 58 of them on names in this universe.
    wanted = [row[0] for row in uni]
    mc = MC.fetch_session_closes(session, wanted)
    # Asked ONLY when there is something to guard — the guard is the price of the
    # splice, not a standing cost of the pass.
    ca = MC.corp_action_tickers(session) if mc.ok else MC.CorpActions(session)
    # FAIL CLOSED. An incomplete corp-action read cannot tell "no name had an
    # action today" from "we did not get to look", and splicing on the second
    # would put a split-day price on a pre-split history. Guard down → store
    # only, disclosed, for the WHOLE pass.
    splice = bool(mc.ok and ca.complete)
    degraded = None if splice else (mc.reason or ca.reason or "unavailable")
    if not splice:
        _warn(f"same-day close fill is OFF ({degraded}) — the board is store-only "
              "and its coverage is whatever the store had at pass time")
    filled: set[str] = set()

    verdicts: dict[str, dict] = {}
    closes: dict[str, Any] = {}
    through: dict[str, str] = {}
    display: dict[str, dict] = {}
    skipped: dict[str, int] = {}
    for ticker, close, _high, name, sector in uni:
        # The nightly's B1 guard (_authority_admits): a delisted name must never
        # enter a scoring-authority collection. The demote-map half of that guard
        # is not reachable here — it is derived from the per-name analyze pass
        # this lane deliberately skips — but this half is cheap and standalone,
        # and the vintage half is covered more strictly below: the nightly
        # demotes a frozen feed, while this pass requires TODAY's bar outright.
        if delisted_symbols.is_delisted(ticker):
            skipped["delisted"] = skipped.get("delisted", 0) + 1
            continue
        if close is None or getattr(close, "empty", True):
            skipped["no_close"] = skipped.get("no_close", 0) + 1
            continue
        last = close.index[-1]
        through[ticker] = (last.date() if hasattr(last, "date") else last).isoformat()
        # A name whose newest bar is not TODAY has not printed today's close on
        # THIS STORE yet. It is never carried at yesterday's price — a board that
        # silently mixes vintages is the defect W-L0 gate 3 exists to stop — so
        # it is either given today's real close from the vendor, or skipped.
        #
        # THE STORE'S OWN TODAY-BAR ALWAYS WINS: this branch is not entered at
        # all when the store already has today. Basis consistency is why —
        # a store bar and the rest of that store's history come from one vendor
        # on one convention, and replacing it with another vendor's print to gain
        # nothing would introduce a seam where there is currently none.
        if through[ticker] != session:
            fill = mc.closes.get(ticker) if splice else None
            # Only ever forward. A store whose newest bar POSTDATES the session
            # (a replay of an old session) must not have an older row appended
            # after it — that would build a non-monotone index the gate reads
            # positionally.
            if fill is None or through[ticker] > session:
                skipped["no_todays_bar"] = skipped.get("no_todays_bar", 0) + 1
                continue
            if ticker in ca.tickers:
                # Counted only when a fill EXISTED and was refused, so this
                # number means "the guard darked N names" rather than doubling as
                # a tally of names nobody had a price for anyway.
                skipped["corp_action_today"] = skipped.get("corp_action_today", 0) + 1
                continue
            close = _with_session_close(close, session, fill)
            through[ticker] = session
            filled.add(ticker)
        verdict = signal_gate.gate(ticker, close)
        verdicts[ticker] = verdict
        closes[ticker] = close

        # Display facts, gathered ONLY for names the gate admits — the same
        # `is_buyable` call build_board ranks on, so the two sets agree. The
        # universe is ~1,660 names and the board is ~130, so this skips ~1,530
        # lookups on a lane with ~30 minutes of the 18:30 SLA to spend.
        if signal_gate.is_buyable(verdict):
            px = close.iloc[-1]
            display[ticker] = {
                "name": name,
                # NULL BY RULING, not by reachability (2026-08-09). A committed
                # 1,583-ticker map exists (config/us_names_zh.json) and this
                # lane could read it — but the nightly's US cards pass no
                # `name_zh` at all, so filling it here would flip a company's
                # NAME between languages overnight: 苹果 in the evening, Apple
                # Inc in the morning. This whole surface exists to answer "which
                # board am I looking at"; a name that changes language attacks
                # that question, and it would land on exactly the readers the
                # stamp is for. Evening/morning consistency outranks evening-only
                # zh quality. Wiring the map into the NIGHTLY is the real fix —
                # it changes every US card, so it needs its own PR and its own
                # visual proof, not a side effect of the evening board.
                "name_zh": None,
                # A sector LABEL, which is a mapping. NOT the sector-neutralised
                # `edge` leg, which needs a full-universe cross-section and stays
                # in OMITTED_LEGS — the two are different objects that share a
                # word. `tr` is the same call the nightly template makes, so this
                # one carries no evening/morning inconsistency.
                "sec": sector,
                "sec_zh": tr(sector) if sector else None,
                # NaN never reaches the payload: json.dumps(allow_nan=False)
                # would raise on it and take the whole publish down, and "$nan"
                # would render on the card if it did not.
                "price": None if pd.isna(px) else float(px),
                # NULL BY RULING (2026-08-09), on measured cost/benefit — see
                # `card_row`'s note. Not a TODO and not a cap: if the design
                # later needs charts, the move is a SEPARATE one-shot artifact
                # fetched only when the stamp qualifies, never a fatter poll.
                "spark": None,
            }

    # Equities and 24/7 crypto are read on their OWN calendars. One mixed panel
    # takes a single global .iloc[-1] and drops every ticker whose latest cell is
    # NaN — measured 3 readings instead of 1,662 — which zeroes the runway leg
    # outright. build_stock_library carries the same split for the same reason.
    ext_by: dict[str, Any] = {}
    if closes:
        panel = pd.DataFrame(closes)
        eq, cx = extension_panels(panel)
        ext_by.update(extension_signals(eq))
        if not cx.empty:
            ext_by.update(extension_signals(cx))

    # PROVENANCE, additively. Every key here is a fact about WHERE the closes the
    # board scored came from — not a score, not a word, and nothing an existing
    # consumer reads. `close_finalized` is a claim about the whole board, so it
    # is true when nothing was filled at all (every close is a settled store bar)
    # and it follows the fill's own finality otherwise: a grouped daily bar is
    # the session's settled aggregate, a snapshot read minutes after the close is
    # the best answer available at that moment and may still be revised.
    close_meta: dict[str, Any] = {
        "close_source": {"store": len(verdicts) - len(filled),
                         "massive": len(filled)},
        "close_observed_at": mc.observed_at or None,
        "close_basis": MC.BASIS,
        "close_finalized": (not filled) or bool(mc.finalized),
    }
    if filled:
        close_meta["close_fill_source"] = mc.source
    if degraded:
        close_meta["close_degraded"] = degraded

    return {"verdicts": verdicts, "ext_by": ext_by, "adjustment_by": adjustment_by,
            "price_through": through, "display_by": display,
            "universe_n": len(uni), "skipped": skipped,
            "close_meta": close_meta}


def build_payload(session: str, now: datetime, inputs: dict[str, Any]) -> dict:
    return CB.build_board(
        inputs["verdicts"], inputs["ext_by"],
        session=session, built_at=now,
        adjustment_by=inputs["adjustment_by"],
        price_through=inputs["price_through"],
        # Absent (a collector that predates W-L1d, a replay) → the payload is
        # honestly not card-complete rather than card-complete-with-holes.
        display_by=inputs.get("display_by"),
        universe_n=inputs["universe_n"],
        skipped=inputs["skipped"],
        # Absent for a collector that predates PR-A (a replay, a test fixture) —
        # the payload then simply carries no close-provenance block rather than
        # an invented one.
        close_meta=inputs.get("close_meta"),
    )


def publish_served(path: Path, payload: dict[str, Any]) -> bool:
    """Write the served copy ATOMICALLY. Returns success; never raises.

    Temp-file-then-rename in the TARGET directory: ``os.replace`` is atomic
    within a filesystem, so a reader sees the previous whole artifact or the new
    whole artifact and never a truncated one. A pass that cannot write leaves
    the previous copy exactly where it was — a stale-but-whole payload is
    self-describing through its own ``as_of``; a half-written one is a parse
    error on a live page.

    The directory is NEVER created. Its absence means this host has no live
    plane, and creating one would hand the edge a directory to serve nothing
    out of.
    """
    if os.environ.get(NO_PUBLISH_ENV, "").strip() not in ("", "0", "false"):
        _warn(f"{NO_PUBLISH_ENV} is set — refusing to write {path}")
        return False
    parent = path.parent
    if not parent.is_dir():
        _notice(f"{parent} is absent — no live plane on this host, so no served "
                "copy (R2 is unaffected)")
        return False
    tmp_name: str | None = None
    try:
        # Serialise BEFORE creating the temp file: a payload that will not
        # encode must not leave a stray dot-file beside a live artifact.
        body = json.dumps(payload, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
            os.fchmod(fh.fileno(), 0o644)
        os.replace(tmp_name, path)
        tmp_name = None
        print(f"{_TAG} served {path} ({len(body)} bytes)", flush=True)
        return True
    except Exception as exc:  # noqa: BLE001
        _warn(f"served copy {path} not written ({exc}) — the previous copy stands")
        return False
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def already_published(session: str, *, fetch=None) -> bool:
    """True when this session's board is already on the plane.

    The DST cron pair fires twice a year-round, so one of the two lines always
    lands at the wrong ET hour: under EDT the 21:20-UTC line is 17:20 ET, an
    hour AFTER the real pass. Without this it would recompute over the same
    closes and republish, resetting the artifact's mtime and — worse — moving
    the sentinel's first-fresh-at stamp off the pass that actually made the SLA.
    Mirrors closing-bell.yml's stamp dedup, on the artifact instead of a file.

    ``fetch`` resolves at CALL time, not at def time: a default of
    ``r2io.get_json`` would bind the function object at import and make the
    boundary unpatchable, so every test would silently exercise the real R2.
    """
    fetch = fetch or r2io.get_json
    return ((fetch(BOARD_KEY) or {}).get("as_of") == session)


def run(*, now: datetime, dry_run: bool = False, force: bool = False,
        served: str | None = SERVED_PATH,
        collector=collect, published=already_published) -> int:
    """One close pass. Returns 0 on any outcome that is not a lane fault."""
    session = session_date(now)
    if session is None:
        _notice("not a NYSE session day — no evening board (this is not a fault)")
        return 0
    if not force and published(session):
        _notice(f"{session} board already published — nothing to do "
                "(the off-season DST cron line)")
        return 0

    inputs = collector(session)
    payload = build_payload(session, now, inputs)
    meta = payload["meta"]
    contract = payload["consumer_contract"]
    print(f"{_TAG} {session}: {meta['admitted_n']} admitted of "
          f"{meta['evaluated_n']} evaluated (universe {meta['universe_n']}); "
          f"skipped {meta['skipped'] or '{}'}; cards {contract['cards_n']} "
          f"complete={contract['card_complete']}", flush=True)
    # The coverage line, printed beside the board it explains: `evaluated_n` is
    # the number the coverage defect showed up in, and the split between store
    # and vendor closes is what makes a change in it readable rather than merely
    # observable.
    if meta.get("close_source"):
        print(f"{_TAG} closes: {meta['close_source']} "
              f"basis={meta.get('close_basis')} "
              f"final={meta.get('close_finalized')} "
              f"src={meta.get('close_fill_source')}", flush=True)
    # An admitted name the reader will not see is a fact the operator should
    # learn from the run, not from a support ticket.
    if contract["cards_dropped_n"]:
        _warn(f"{contract['cards_dropped_n']} admitted name(s) carry no card "
              "(a required display field was missing) — they are on the board "
              "of record but not in the client's grid")

    if not meta["evaluated_n"]:
        # Zero evaluable names is a broken store, not an empty market. Publishing
        # an empty board would read on the page as "nothing qualifies tonight",
        # which is a claim this pass has no evidence for.
        _warn(f"no name carried a {session} close — publishing nothing")
        return 0

    if dry_run:
        print(f"dry-run: nothing published ({len(json.dumps(payload))} bytes)",
              flush=True)
        return 0

    if not r2io.put_json(BOARD_KEY, payload):
        _warn(f"R2 PUT {BOARD_KEY} failed — the VPS mirror will not see this pass")
    if served:
        # Independent failure domains: R2 is the pipeline artifact and the file
        # is the product path, so one hiccuping must not stale the other.
        publish_served(Path(served), payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evening close-pass provisional board")
    ap.add_argument("--now", default=None, help="ISO clock override (naive = UTC)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="republish even if this session's board is already up")
    ap.add_argument("--served-path", default=os.environ.get("CLOSE_PASS_SERVED_PATH",
                                                            SERVED_PATH),
                    help="'' to publish to R2 only (the runner's normal case)")
    args = ap.parse_args(argv)

    if args.now:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        # Naive stamps are UTC BY CONTRACT (the repo-wide #2463 convention).
        now = (now.replace(tzinfo=timezone.utc) if now.tzinfo is None
               else now.astimezone(timezone.utc))
    else:
        now = datetime.now(timezone.utc)
    return run(now=now, dry_run=args.dry_run, force=args.force,
               served=args.served_path or None)


if __name__ == "__main__":
    sys.exit(main())
