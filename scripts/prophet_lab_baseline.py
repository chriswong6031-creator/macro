#!/usr/bin/env python3
"""scripts/prophet_lab_baseline.py — mint the Prophet Operator Lab's
observation-baseline marker (LAB-0 §6 step 3, "Radar live commissioning";
`research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md` §4/§6).

WHAT THIS MARKER IS AND WHY MINTING IT IS DANGEROUS TO GET WRONG
------------------------------------------------------------------
`engine/prophet_lab/observation.py`'s honesty rule: with NO baseline marker,
every event the Lab shows is `retrospective_seed` (fail-honest default). Once
a baseline exists, an event is `live_forward` — genuinely new, evidence-
eligible, eligible for a measured Lab->Prophet lead — only when its FIRST
OBSERVED spool `pass_ts` falls at or after `baseline_started_at` AND the
spool's own earliest surviving envelope reaches back at least that far
(`engine.prophet_lab.sources.baseline_coverage_verified`, the S1 fail-CLOSED
check). That second half is the trap this CLI exists to close: a baseline
minted BEFORE any real spooled pass exists has no coverage evidence to verify
against, so `baseline_coverage_verified` degrades to `False` and every event
STAYS `retrospective_seed` forever -- a Lab that looks provisioned but is
permanently all-seed, with no error anywhere to say so.

So this CLI REFUSES to mint unless it can read at least one real spooled
pass with a `pass_ts` it can parse to a tz-aware instant (never a naive one
-- `engine.prophet_lab.timeparse.parse_instant`'s fail-closed contract,
unchanged and NOT weakened here), and the marker it mints,
`baseline_started_at`, is always "now" -- a timestamp strictly AFTER both the
earliest and the latest pass_ts actually observed, so the very first read
back through the API already has verifiable coverage.

TRANSPORT
---------
Reads through `engine.prophet_lab.sources.resolve_radar_spool` -- the exact
R2-first-else-local ladder the production API uses (`engine.entry_radar.spool`
under the hood), never a second, divergent read path. `--spool-dir` overrides
the local fallback half; production credentials (`$R2_ENDPOINT`/
`$R2_ACCESS_KEY_ID`/`$R2_SECRET_ACCESS_KEY`) are read from the environment,
same as the API process.

WRITE TARGET
------------
`$PROPHET_LAB_OBSERVATION_BASELINE_PATH` (or `--baseline-path`) -- a
runtime/state-plane file the API server reads, e.g.
`/var/lib/macro-live/state/prophet_lab/observation_baseline.json`. Never a
`data/` path: this is operator-provisioned Lab state, not a nightly ledger
(nightly is the sole `data/` advancer, house law, unrelated to this file).

USAGE
-----
    python3 scripts/prophet_lab_baseline.py                     # dry run (default)
    python3 scripts/prophet_lab_baseline.py --write              # actually mint
    python3 scripts/prophet_lab_baseline.py --spool-dir /var/lib/macro-live/state/entry_radar/spool \\
        --baseline-path /var/lib/macro-live/state/prophet_lab/observation_baseline.json --write

Exit 0 on a successful dry-run report OR a successful mint; exit 1 on any
refusal (no baseline path configured, no readable spooled pass, or an
ordering violation).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# UNCONDITIONAL, and at position 0 on purpose — the same strong pin
# scripts/entry_radar_live_pack.py carries (tests/test_check_script_import_pinning.py
# rejects a conditional `if str(ROOT) not in sys.path` form: when ROOT is
# already on the path but sits behind a foreign package, that guard silently
# skips the insert and the foreign package wins the import).
sys.path.insert(0, str(REPO_ROOT))

from engine.prophet_lab import sources  # noqa: E402
from engine.prophet_lab.timeparse import parse_instant  # noqa: E402

_SPOOL_DIR_ENV_PRIMARY = "PROPHET_LAB_RADAR_SPOOL_DIR"
_SPOOL_DIR_ENV_FALLBACK = "ENTRY_RADAR_SPOOL_DIR"  # Radar's own local-spool var
_BASELINE_PATH_ENV = "PROPHET_LAB_OBSERVATION_BASELINE_PATH"


def _iso(instant: datetime) -> str:
    """Tz-aware UTC instant -> the exact ISO-8601 ``Z``-suffixed shape every
    producer this package reads is documented to emit (see
    ``engine/prophet_lab/timeparse.py``'s module docstring)."""
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _resolve_spool_dir(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    raw = os.environ.get(_SPOOL_DIR_ENV_PRIMARY, "").strip()
    if raw:
        return Path(raw)
    raw = os.environ.get(_SPOOL_DIR_ENV_FALLBACK, "").strip()
    return Path(raw) if raw else None


def _resolve_baseline_path(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    raw = os.environ.get(_BASELINE_PATH_ENV, "").strip()
    return Path(raw) if raw else None


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911
    ap = argparse.ArgumentParser(
        description="Mint the Prophet Operator Lab's observation-baseline "
                     "marker (LAB-0 §6 step 3). Refuses unless a real "
                     "spooled pass is readable.",
    )
    ap.add_argument("--spool-dir", default=None,
                    help=f"local-fallback spool dir (default: "
                         f"${_SPOOL_DIR_ENV_PRIMARY}, else ${_SPOOL_DIR_ENV_FALLBACK}); "
                         f"R2 is still tried FIRST when credentials are set")
    ap.add_argument("--baseline-path", default=None,
                    help=f"where to mint the marker (default: ${_BASELINE_PATH_ENV})")
    ap.add_argument("--write", action="store_true",
                    help="actually mint the marker (default: dry run, report only)")
    ap.add_argument("--as-of", default=None,
                    help="TESTING/REHEARSAL ONLY: override the minted "
                         "baseline_started_at instant (ISO-8601 with an "
                         "explicit UTC offset). Production always mints "
                         "the real wall-clock now.")
    args = ap.parse_args(argv)

    baseline_path = _resolve_baseline_path(args.baseline_path)
    if baseline_path is None:
        print(
            f"[prophet_lab_baseline] REFUSING: no baseline path configured "
            f"(--baseline-path or ${_BASELINE_PATH_ENV}). Nothing to mint "
            f"and nowhere to report a dry run against.",
            file=sys.stderr,
        )
        return 1
    print(f"[prophet_lab_baseline] baseline target path: {baseline_path}")

    spool_dir = _resolve_spool_dir(args.spool_dir)
    print(f"[prophet_lab_baseline] local-fallback spool dir: "
          f"{spool_dir if spool_dir is not None else '(unconfigured)'}")

    result = sources.resolve_radar_spool(spool_dir)
    print(f"[prophet_lab_baseline] backend resolved: {result.backend}"
          + (f"  (error: {result.error})" if result.error else ""))
    print(f"[prophet_lab_baseline] objects seen: {result.files_seen}  "
          f"skipped: {result.envelopes_skipped}  "
          f"envelopes read: {len(result.envelopes)}")

    earliest_raw = sources.earliest_pass_ts(result.envelopes)
    latest_envelope = sources.latest_envelope(result.envelopes)
    latest_raw = latest_envelope.get("pass_ts") if latest_envelope else None
    earliest_instant = parse_instant(earliest_raw) if earliest_raw else None
    latest_instant = parse_instant(latest_raw) if latest_raw else None

    if earliest_instant is None or latest_instant is None:
        print(
            "[prophet_lab_baseline] REFUSING: no real spooled pass with a "
            "parseable, tz-aware pass_ts was found. Minting a baseline now "
            "would have no verifiable coverage evidence behind it -- the "
            "API's S1 fail-closed check (baseline_coverage_verified) would "
            "degrade every event to retrospective_seed forever, with no "
            "visible error anywhere. Wait for at least one real Radar pass "
            "to spool, then re-run.",
            file=sys.stderr,
        )
        return 1

    print(f"[prophet_lab_baseline] earliest observed pass_ts: {earliest_raw}")
    print(f"[prophet_lab_baseline] latest observed pass_ts:   {latest_raw}")

    if args.as_of:
        minted_instant = parse_instant(args.as_of)
        if minted_instant is None:
            print(
                f"[prophet_lab_baseline] REFUSING: --as-of={args.as_of!r} does "
                f"not parse to a tz-aware ISO-8601 instant (an explicit UTC "
                f"offset is required -- never guess UTC on a naive string).",
                file=sys.stderr,
            )
            return 1
    else:
        minted_instant = datetime.now(timezone.utc)

    # Strictly-after-first-pass ordering (LAB-0 §4/§6): the minted
    # baseline_started_at must postdate BOTH the earliest and the latest
    # observed pass -- never merely "not before the latest", which could
    # still tie a pass_ts and make coverage ambiguous at the boundary.
    if minted_instant <= earliest_instant or minted_instant <= latest_instant:
        print(
            f"[prophet_lab_baseline] REFUSING: the candidate "
            f"baseline_started_at ({_iso(minted_instant)}) is not strictly "
            f"after both the earliest ({earliest_raw}) and latest "
            f"({latest_raw}) observed pass_ts. Minting here would violate "
            f"the ordering the S1 coverage check depends on.",
            file=sys.stderr,
        )
        return 1

    marker = {
        "schema": sources.BASELINE_SCHEMA,
        "baseline_started_at": _iso(minted_instant),
    }
    print(f"[prophet_lab_baseline] would mint: {json.dumps(marker, indent=2)}")

    if not args.write:
        print(
            "[prophet_lab_baseline] DRY RUN (default) -- nothing written. "
            "Re-run with --write to mint.",
        )
        return 0

    body = json.dumps(marker, indent=2).encode("utf-8") + b"\n"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = baseline_path.with_name(baseline_path.name + ".tmp")
    tmp.write_bytes(body)
    os.replace(tmp, baseline_path)
    print(f"[prophet_lab_baseline] MINTED: {baseline_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
