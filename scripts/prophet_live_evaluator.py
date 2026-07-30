"""scripts/prophet_live_evaluator.py — the */5 Prophet Live intraday pass (P0 D3).

Loads tonight's armed pack from R2, merges the freshest delayed quote view through
the estate's single quote seam (:func:`engine.marketing.live_verify.load_live_quotes`),
runs the state machine in :mod:`engine.prophet_live.live_states`, and publishes two
runtime artifacts: the full state map and, when anything actually moved, an
object-per-pass event spool row set.

    python -m scripts.prophet_live_evaluator [--dry-run] [--now ISO] [--root PATH]

LEDGER LAW (G0.2). This lane writes NOTHING under ``data/`` and commits nothing. It
runs 80+ times a session; the nightly reconciler is the sole writer of
``data/prophet_live/``, and the nightly build remains the only thing that confirms,
grades or advances a ledger. The workflow has no write permission and no git step.

HONEST DEGRADATION (G0.3). Three independent ways to be dark, all named:
  * pack missing            → whole artifact ``status:"dark" reason:"no_pack"``
  * pack ``as_of`` is not the last completed session → ``"stale_pack"``; yesterday's
    triggers are never evaluated against today's tape
  * per-name: no quote, quote older than ``quote_max_age_min``, an irregular gate,
    or a name the pack could not probe → that NAME goes dark with its reason while
    the rest of the artifact stays live.
No path invents a state, and nothing here says fired, confirmed or refuted.

NO PANDAS ON THIS PATH. The workflow installs ``pyyaml boto3`` only.
``live_verify`` imports pandas lazily (inside its earnings helper, which this lane
never calls) and ``live_states``/``r2io`` are stdlib plus a lazy boto3, so the whole
import closure is thin by construction.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
if _CODE_ROOT not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, _CODE_ROOT)

from engine.marketing import live_verify as LV  # noqa: E402
from engine.prophet_live import live_states as LS  # noqa: E402
from engine.prophet_live import r2io  # noqa: E402

log = logging.getLogger("prophet_live_evaluator")


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


def run(root: Path, *, now: datetime | None = None, dry_run: bool = False,
        cfg: dict[str, Any] | None = None) -> int:
    """One evaluator pass. Returns a process exit code (0 unless a write was expected
    and impossible)."""
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    conf = cfg if cfg is not None else load_config(root)
    lc = LS.live_cfg(conf)

    if not LS.in_window(ts, lc):
        w = lc.get("window_et") or {}
        print(f"::notice title=prophet-live::outside the {w.get('start')}-{w.get('end')} "
              f"ET weekday window ({ts.strftime('%Y-%m-%dT%H:%MZ')}) — standing down",
              flush=True)
        return 0

    s3 = r2io.client()
    if s3 is None:
        print("::warning title=prophet-live::no R2 credentials — reading the public "
              "mirror, publishing nothing this pass", flush=True)

    pack = r2io.get_json(r2io.PACK_KEY, s3=s3)
    prev = r2io.get_json(r2io.LIVE_KEY, s3=s3, allow_public=False)

    live = LV.load_live_quotes(root)
    quotes = live.get("quotes") if isinstance(live.get("quotes"), dict) else {}
    delay_min = None
    try:
        delay_min = int(((conf.get("live") or {}).get("delayed_min")))
    except (TypeError, ValueError):
        delay_min = None

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
        print(f"prophet-live pass={m['pass_ts']} pack_as_of={m['pack_as_of']} "
              f"quotes={m['quotes_n']}@{m['quote_asof']} src={live.get('source')} "
              f"states={m['states']} dark={m['dark_counts']} events={m['events_n']}",
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

    if s3 is None:
        return 0
    ok = r2io.put_json(r2io.LIVE_KEY, art, s3=s3)
    if not ok:
        print("::warning title=prophet-live::live artifact PUT failed — the next pass "
              "loses its debounce history", flush=True)
    if events:
        stamp = LS.et_clock(ts).strftime("%H%M%S")
        key = r2io.events_key(m["session_et"], stamp)
        spool = {"schema": "prophet_live.events/v1", "pass_ts": m["pass_ts"],
                 "session_et": m["session_et"], "pack_as_of": m.get("pack_as_of"),
                 "quote_asof": m.get("quote_asof"), "events": events}
        if not r2io.put_json(key, spool, s3=s3):
            print(f"::warning title=prophet-live::event spool PUT {key} failed — "
                  f"{len(events)} transitions are not in tonight's evidence", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prophet Live intraday evaluator — provisional states off the armed pack.")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="evaluate and print; write nothing to R2")
    parser.add_argument("--now", default=None,
                        help="ISO timestamp override for the pass clock (tests / replays)")
    parser.add_argument("--root", default=None, help="repo root (default: this script's parent)")
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
        return run(root, now=now, dry_run=bool(args.dry_run))
    except Exception as exc:  # noqa: BLE001
        # A lane that turns 80 runs a day red is noise; a pass that cannot say
        # anything simply says nothing and the artifact keeps its previous stamp.
        print(f"::warning title=prophet-live::pass failed: {exc}", flush=True)
        log.warning("prophet_live_evaluator: unexpected failure", exc_info=True)
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
