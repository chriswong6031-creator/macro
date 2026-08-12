"""Merge superseded ticker keys onto their current key in the track-record ledger.

THE ACT THIS PERFORMS, STATED PLAINLY: it rewrites a committed, append-only measurement
ledger, and the file comes out with FEWER ROWS than it went in with. That is why it is a
separate script, dry-run by default, and refuses to write unless its own losslessness
receipt is clean — not a step inside the nightly.

WHY IT IS NOT A REPAINT
-----------------------
`data/signal_archive/track_record.parquet` is append-only by charter (RC-R2 / keep-FIRST)
and the charter's purpose is ANTI-REPAINT: the engine must not quietly rewrite history to
grade itself more kindly. A key migration is a different act. Nothing measured changes —
the rows being removed are bit-identical copies of rows that stay, filed under a string
the operator has ratified as the same company (`quality.ticker_key_migrations`). The
merge is keep-FIRST onto the CURRENT key, exactly as the nightly would have filed them
had the rename been known.

The receipt is enforced, not asserted (`engine.ledger_identity.migration_receipt`):

  keys_without_counterpart   a superseded key with no row under the current key. Those
                             rows are RE-KEYED (carried across), never dropped.
  cells_lost                 a cell where the superseded row holds a value and its
                             counterpart is NULL. Any of these and `--apply` REFUSES:
                             a keep-FIRST merge would lose that measurement.
  identity_conflicts         a cell where both hold values and they DISAGREE. Any of
                             these and the two keys are not one measurement — `--apply`
                             REFUSES and the identity itself needs re-examining.

Measured on the 2026-08-12 ledger for SATS->ECHO: 128 rows, zero orphan keys, zero cells
lost, zero conflicts — all 39 identity/entry columns byte-identical, and every maturation
divergence runs ECHO's way (SATS's price store is gone and SATS is absent from the
dead-name registry, so its copies can never mature again). Effect on the file: 58,660 ->
58,532 rows. Effect on the headline statistics: take hit-rate 0.718973 -> 0.718911, take
mean fwd_mdd_60 -0.052263 -> -0.052217. Slightly WORSE on hit rate, slightly better on
drawdown — mixed in direction and ~1e-4 in size, which is what "removed a double count"
looks like and what "flattered the record" does not.

USAGE
    python scripts/migrate_track_record_keys.py              # dry run: receipt + diff, no write
    python scripts/migrate_track_record_keys.py --json       # same, machine-readable
    python scripts/migrate_track_record_keys.py --apply      # write (operator ratification)

EXIT CODES
    0  nothing to migrate, or a dry run that found a clean migration
    3  a migration is pending and NOT lossless — needs a human before it can proceed
    2  crash
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine import ledger_identity  # noqa: E402

log = logging.getLogger("migrate_track_record_keys")

DEFAULT_LEDGER = _ROOT / "data" / "signal_archive" / "track_record.parquet"


def plan(df: pd.DataFrame, migrations: dict[str, str]) -> dict:
    """What a migration would do to `df`, with the losslessness receipt per pair.

    Pure — inspects, never writes. `blocked` is the pairs whose receipt is dirty; while
    any exist the whole migration is refused (a partial rewrite of an append-only ledger
    is worse than none: it leaves the file in a state no charter describes).
    """
    findings = ledger_identity.find_declared_duplicates(df, migrations)
    pairs, blocked = [], []
    for f in findings:
        old, new = f["superseded"], f["current"]
        receipt = ledger_identity.migration_receipt(df, old, new)
        entry = {**f, "receipt": receipt}
        pairs.append(entry)
        if not receipt["lossless"]:
            blocked.append(entry)
    rows_in = int(len(df))
    # A superseded row disappears only when the current key already holds its (date, type);
    # one without a counterpart is re-keyed and survives. So the file shrinks by exactly
    # (superseded rows - orphan keys) per pair.
    rows_removed = sum(e["receipt"]["superseded_rows"]
                       - len(e["receipt"]["keys_without_counterpart"])
                       for e in pairs)
    return {
        "ledger_rows_before": rows_in,
        "ledger_rows_after": rows_in - rows_removed,
        "rows_merged": rows_removed,
        "rows_rekeyed": sum(len(e["receipt"]["keys_without_counterpart"]) for e in pairs),
        "pairs": pairs,
        "blocked": blocked,
        "clean": bool(pairs) and not blocked,
    }


def migrate(df: pd.DataFrame, migrations: dict[str, str]) -> pd.DataFrame:
    """Return `df` with every superseded key merged onto its current key, keep-FIRST.

    A superseded row whose (date, type) already exists under the current key is DROPPED
    (it is the duplicate); one whose key does not exist there is RE-KEYED and kept. Row
    order of the surviving frame is preserved so the file stays diff-legible.
    """
    if df.empty or not migrations:
        return df
    tick = df["ticker"].astype(str)
    resolved = tick.map(lambda t: ledger_identity.current_key(t, migrations))
    was_superseded = resolved != tick

    if not bool(was_superseded.any()):
        return df

    out = df.copy()
    out["ticker"] = resolved
    # keep-FIRST, but the CURRENT key's row is the one to keep — it is the copy that can
    # still mature. Stable-sort the superseded rows to the back, drop_duplicates(first),
    # then restore the original order of whatever survived.
    out["_orig_pos"] = range(len(out))
    out["_is_superseded"] = was_superseded.to_numpy()
    out = out.sort_values(["_is_superseded", "_orig_pos"], kind="stable")
    out = out.drop_duplicates(subset=list(ledger_identity.KEY_COLS), keep="first")
    out = out.sort_values("_orig_pos", kind="stable").drop(
        columns=["_orig_pos", "_is_superseded"]
    )
    return out.reset_index(drop=True)


def _emit_text(p: dict, ledger: Path, applied: bool) -> None:
    if not p["pairs"]:
        print(f"[migrate_track_record_keys] {ledger}: no superseded keys carry rows — "
              "nothing to migrate.")
        return
    print(f"[migrate_track_record_keys] {ledger}")
    print(f"  rows {p['ledger_rows_before']} -> {p['ledger_rows_after']} "
          f"({p['rows_merged']} merged, {p['rows_rekeyed']} re-keyed)")
    for entry in p["pairs"]:
        r = entry["receipt"]
        print(f"  {entry['superseded']} -> {entry['current']}: "
              f"{r['superseded_rows']} superseded rows, {entry['shared_keys']} shared keys, "
              f"span {entry['span'][0]}..{entry['span'][1]}")
        print(f"      lossless={r['lossless']}  orphan_keys={len(r['keys_without_counterpart'])}  "
              f"cells_lost={len(r['cells_lost'])}  conflicts={len(r['identity_conflicts'])}  "
              f"provenance_only={len(r['provenance_divergences'])}")
        for c in r["provenance_divergences"][:5]:
            print(f"        provenance {c['key']} {c['column']}: "
                  f"{c['superseded_value']} -> {c['current_value']} (bookkeeping, not a veto)")
        for c in r["cells_lost"][:5]:
            print(f"        LOST  {c['key']} {c['column']}={c['superseded_value']}")
        for c in r["identity_conflicts"][:5]:
            print(f"        CONFLICT {c['key']} {c['column']}: "
                  f"{c['superseded_value']} != {c['current_value']}")
    if applied:
        print("  APPLIED — ledger rewritten.")
    elif p["clean"]:
        print("  DRY RUN — migration is lossless. Re-run with --apply to write it.")
    else:
        print("  DRY RUN — migration is NOT lossless and --apply would refuse it.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER,
                    help=f"ledger parquet (default: {DEFAULT_LEDGER})")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE the migration (operator ratification; refuses if not lossless)")
    ap.add_argument("--json", action="store_true", help="emit the plan as JSON")
    args = ap.parse_args(argv)

    try:
        if not args.ledger.exists():
            print(f"[migrate_track_record_keys] {args.ledger} absent — nothing to do.")
            return 0
        df = pd.read_parquet(args.ledger)
        migrations = ledger_identity.load_migrations()
        p = plan(df, migrations)

        applied = False
        if args.apply and p["pairs"]:
            if not p["clean"]:
                if args.json:
                    print(json.dumps({**p, "applied": False}, indent=1, default=str))
                else:
                    _emit_text(p, args.ledger, applied=False)
                print("::error title=track-record-key-migration::migration REFUSED — the "
                      "losslessness receipt is dirty (cells the merge would lose, or "
                      "cells the two keys disagree on). Resolve the identity before "
                      "rewriting an append-only ledger.", flush=True)
                return 3
            out = migrate(df, migrations)
            # Belt-and-braces: the plan predicted the row count; a mismatch means the
            # merge did something the receipt did not describe, so do not write.
            if len(out) != p["ledger_rows_after"]:
                print(f"::error title=track-record-key-migration::planned "
                      f"{p['ledger_rows_after']} rows, merge produced {len(out)} — "
                      "refusing to write.", flush=True)
                return 3
            out.to_parquet(args.ledger, index=False)
            applied = True

        if args.json:
            print(json.dumps({**p, "applied": applied}, indent=1, default=str))
        else:
            _emit_text(p, args.ledger, applied=applied)
        if p["pairs"] and not p["clean"]:
            return 3
        return 0
    except Exception:  # noqa: BLE001 — a crash is exit 2; findings never raise
        log.exception("[migrate_track_record_keys] crashed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
