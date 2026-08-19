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
`baseline_started_at`, is always "now" -- a timestamp STRICTLY AFTER the
LATEST pass_ts actually observed (which, since the latest is by definition
never earlier than the earliest, is also strictly after the earliest -- the
two are not independent conditions; only the latest needs checking). The
very first read back through the API therefore already has verifiable
coverage.

HOST REQUIREMENT: run this ON THE SAME HOST as the spool WRITER (the live
5-min evaluator / pack builder), not from an operator's laptop or a CI
runner. "Now" is this process's OWN wall clock, and `baseline_started_at`'s
entire safety property rests on that clock genuinely postdating the writer's
most recent `pass_ts` -- a skewed clock on a different machine can silently
violate that. See the skew check below, and the commissioning runbook.

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

An EXISTING valid marker is never silently overwritten -- `--remint` is
required (S5): an accidental second `--write` would otherwise reset every
event observed since the original baseline back to `retrospective_seed`,
destroying accrued live_forward history with no undo.

USAGE
-----
    python3 scripts/prophet_lab_baseline.py                     # dry run (default)
    python3 scripts/prophet_lab_baseline.py --write              # actually mint
    python3 scripts/prophet_lab_baseline.py --spool-dir /var/lib/macro-live/state/entry_radar/spool \\
        --baseline-path /var/lib/macro-live/state/prophet_lab/observation_baseline.json --write
    python3 scripts/prophet_lab_baseline.py --write --remint      # deliberate re-mint over an existing marker

Exit 0 on a successful dry-run report OR a successful mint; exit 1 on any
refusal (no baseline path configured, no readable spooled pass, an ordering
violation, an implausible clock skew, an existing marker without --remint,
or a post-write consistency check failure).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
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

#: Review N1: a skew this large between "now" and the latest observed pass
#: is far outside any plausible commissioning workflow (the pack cadence is
#: 5 minutes) and much more likely to mean either a badly wrong --spool-dir
#: (stale/wrong-source data) or a genuinely skewed clock on this host than a
#: deliberately slow operator. Refused rather than warned, per the review.
_IMPLAUSIBLE_SKEW = timedelta(hours=24)


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


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911, PLR0912, PLR0915
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
    ap.add_argument("--remint", action="store_true",
                    help="required (with --write) to overwrite an EXISTING valid "
                         "baseline marker -- review S5: an accidental second "
                         "--write would otherwise silently reset accrued "
                         "live_forward history")
    ap.add_argument("--as-of", default=None,
                    help="TESTING/REHEARSAL ONLY: override the minted "
                         "baseline_started_at instant (ISO-8601 with an "
                         "explicit UTC offset). Production always mints "
                         "the real wall-clock now. Combining with --write "
                         "also requires --i-know-this-is-rehearsal.")
    ap.add_argument("--i-know-this-is-rehearsal", action="store_true",
                    help="required (review S7) alongside --as-of when --write "
                         "is also given -- confirms this run is a deliberate "
                         "rehearsal/test, not production")
    args = ap.parse_args(argv)

    # Review S7: --as-of + --write with no confirmation flag would silently
    # mint a FAKE baseline_started_at in what could be a real production
    # deployment (a copy-pasted rehearsal command, an env var left set).
    if args.as_of and args.write and not args.i_know_this_is_rehearsal:
        print(
            "[prophet_lab_baseline] REFUSING: --as-of combined with --write "
            "requires --i-know-this-is-rehearsal too -- minting a FAKE "
            "baseline_started_at in production would silently corrupt the "
            "Lab's provenance. Drop --as-of (mint the real now) or add "
            "--i-know-this-is-rehearsal for a deliberate rehearsal/test.",
            file=sys.stderr,
        )
        return 1

    baseline_path = _resolve_baseline_path(args.baseline_path)
    if baseline_path is None:
        print(
            "[prophet_lab_baseline] REFUSING: no baseline path configured "
            f"(--baseline-path or ${_BASELINE_PATH_ENV}). Nothing to mint "
            "and nowhere to report a dry run against.",
            file=sys.stderr,
        )
        return 1
    print(f"[prophet_lab_baseline] baseline target path: {baseline_path}")

    # Review S5: never silently overwrite an existing VALID marker. A marker
    # that is absent or already malformed carries no accrued history worth
    # protecting, so only a genuinely readable one gates on --remint.
    existing = sources.read_observation_baseline(baseline_path)
    if existing.baseline is not None:
        print(
            "[prophet_lab_baseline] an EXISTING valid marker is already at "
            f"{baseline_path} (baseline_started_at="
            f"{existing.baseline.get('baseline_started_at')!r})."
        )
        if args.write and not args.remint:
            print(
                "[prophet_lab_baseline] REFUSING: overwriting it would "
                "silently reset every event observed since then back to "
                "retrospective_seed, with no undo. Pass --remint to confirm "
                "this is deliberate.",
                file=sys.stderr,
            )
            return 1

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
                "not parse to a tz-aware ISO-8601 instant (an explicit UTC "
                "offset is required -- never guess UTC on a naive string).",
                file=sys.stderr,
            )
            return 1
    else:
        minted_instant = datetime.now(timezone.utc)

    # Review N1: the ordering guarantee only needs ONE comparison. "Strictly
    # after the LATEST observed pass" already implies "strictly after the
    # earliest" too, since the latest is by construction never earlier than
    # the earliest (sources.latest_envelope / earliest_pass_ts over the SAME
    # envelope set) -- the two were never independent conditions, and a
    # redundant "or ... <= earliest_instant" clause was dead code that could
    # never fire on its own. Also prints the now-vs-latest skew and refuses
    # an implausible one (S2-adjacent hardening, N1): a real clock running
    # normally should show a small positive skew here (the pack cadence is
    # 5 minutes); zero/negative or absurdly large both point at the same
    # underlying risk -- this process's clock does not actually postdate the
    # writer's, which is the ENTIRE safety property this marker rests on.
    skew = minted_instant - latest_instant
    print(f"[prophet_lab_baseline] now - latest_pass skew: {skew}")
    if skew <= timedelta(0):
        print(
            f"[prophet_lab_baseline] REFUSING: the candidate "
            f"baseline_started_at ({_iso(minted_instant)}) is not strictly "
            f"after the latest observed pass_ts ({latest_raw}). This can "
            "mean a bad --as-of value, or genuine CLOCK SKEW between this "
            "host and the spool writer -- run this CLI on the SAME host as "
            "the writer (see the module docstring's HOST REQUIREMENT).",
            file=sys.stderr,
        )
        return 1
    if skew > _IMPLAUSIBLE_SKEW:
        print(
            f"[prophet_lab_baseline] REFUSING: the now-vs-latest-pass skew "
            f"({skew}) is implausibly large for a 5-minute pack cadence. "
            "This usually means --spool-dir (or the resolved R2 backend) is "
            "pointed at stale or wrong-source data, or this host's clock is "
            "skewed relative to the spool writer's. Verify the source before "
            "re-running.",
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

    # Review N1: post-write consistency re-check. The spool could have kept
    # advancing during the brief window between the read above and this
    # write (a concurrently running live evaluator on the same host, the
    # scenario the HOST REQUIREMENT note exists to make rare but not
    # impossible). If a re-read now shows ANY envelope whose pass_ts parses
    # to an instant AT OR AFTER the instant we just minted, the ordering
    # guarantee this marker is supposed to carry can no longer be vouched
    # for with confidence -- remove the just-written marker and hard-fail
    # rather than leave a marker whose own safety property may already be
    # stale the moment it was written.
    recheck = sources.resolve_radar_spool(spool_dir)
    for envelope in recheck.envelopes:
        pass_ts = envelope.get("pass_ts")
        instant = parse_instant(pass_ts) if pass_ts else None
        if instant is not None and instant >= minted_instant:
            baseline_path.unlink(missing_ok=True)
            print(
                f"[prophet_lab_baseline] HARD-FAIL: a post-write re-read found "
                f"an envelope (pass_ts={pass_ts!r}) at or after the just-minted "
                f"baseline_started_at ({_iso(minted_instant)}) -- the spool "
                "kept advancing during the write window, so this marker's "
                "ordering guarantee cannot be trusted. Removed "
                f"{baseline_path}. Re-run once the source is quiet.",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
