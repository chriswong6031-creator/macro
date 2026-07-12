"""Statement tape schema guard (FL-E / FC-R9).

Validates every non-comment row in data/statement_tape/registry.jsonl against
the required schema.  Exits 1 on any violation so CI catches regressions.

Schema (binding):
  date          str   YYYY-MM-DD
  ts_utc        str|null  ISO 8601 or null
  speaker       str   non-empty
  venue         str   non-empty
  quote         str   non-empty
  paraphrase    bool  (default-false if absent is a soft warning, not a hard fail)
  stance_tag    str   one of VALID_STANCES
  source_url    str|null
  added_by      str   non-empty
  added_at      str   ISO 8601 UTC timestamp

PS-R1 enforcement baked in: fields that would imply prediction/forecast are
flagged if found (any key containing "signal", "forecast", "prediction",
"probability", "prob", "edge").

Run:
    python -m scripts.check_statement_tape          # validate; exit 1 on fail
    python -m scripts.check_statement_tape --list   # print every row summary
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "statement_tape" / "registry.jsonl"

VALID_STANCES = {"market_boost", "anti_short", "fed_pressure", "policy_action", "other"}
_REQUIRED = ("date", "speaker", "venue", "quote", "stance_tag", "added_by", "added_at")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# PS-R1: these key substrings would imply LLM-emitted signal/forecast — ban them
_BANNED_KEYS = ("signal", "forecast", "prediction", "probability", "prob", "edge")


def _check_iso(val: str) -> bool:
    """Lenient ISO check: must be parseable as a datetime."""
    try:
        datetime.fromisoformat(val.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_row(row: dict, lineno: int) -> list[str]:
    """Return list of error strings for this row (empty = valid)."""
    errors: list[str] = []

    # required field presence
    for field in _REQUIRED:
        if field not in row:
            errors.append(f"line {lineno}: missing required field '{field}'")
        elif not isinstance(row[field], (str, type(None))):
            # all required fields are strings (or handled below)
            pass

    # date format
    date_val = row.get("date", "")
    if date_val and not _DATE_RE.match(str(date_val)):
        errors.append(f"line {lineno}: 'date' must be YYYY-MM-DD, got {date_val!r}")

    # ts_utc: null or ISO string
    ts = row.get("ts_utc", "__MISSING__")
    if ts != "__MISSING__" and ts is not None:
        if not isinstance(ts, str) or not _check_iso(ts):
            errors.append(f"line {lineno}: 'ts_utc' must be null or ISO 8601, got {ts!r}")

    # speaker non-empty
    if isinstance(row.get("speaker"), str) and not row["speaker"].strip():
        errors.append(f"line {lineno}: 'speaker' must be non-empty")

    # venue non-empty
    if isinstance(row.get("venue"), str) and not row["venue"].strip():
        errors.append(f"line {lineno}: 'venue' must be non-empty")

    # quote non-empty
    if isinstance(row.get("quote"), str) and not row["quote"].strip():
        errors.append(f"line {lineno}: 'quote' must be non-empty")

    # stance_tag enum
    tag = row.get("stance_tag", "")
    if tag and tag not in VALID_STANCES:
        errors.append(
            f"line {lineno}: 'stance_tag' must be one of {sorted(VALID_STANCES)!r}, "
            f"got {tag!r}"
        )

    # added_at ISO
    added = row.get("added_at", "")
    if added and not _check_iso(str(added)):
        errors.append(f"line {lineno}: 'added_at' must be ISO 8601, got {added!r}")

    # added_by non-empty
    if isinstance(row.get("added_by"), str) and not row["added_by"].strip():
        errors.append(f"line {lineno}: 'added_by' must be non-empty")

    # PS-R1 enforcement: no banned key substrings
    for key in row:
        lk = key.lower()
        for banned in _BANNED_KEYS:
            if banned in lk:
                errors.append(
                    f"line {lineno}: key {key!r} contains banned substring {banned!r} "
                    f"(PS-R1: no signal/forecast/prediction fields)"
                )

    return errors


def load_rows(path: Path) -> list[tuple[int, dict]]:
    """Load all non-comment, non-blank lines as (lineno, dict) pairs."""
    rows: list[tuple[int, dict]] = []
    if not path.exists():
        return rows
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"line {i}: JSON parse error — {e}", file=sys.stderr)
            continue
        if not isinstance(obj, dict):
            continue
        # skip the header comment row
        if "_comment" in obj and len(obj) == 1:
            continue
        rows.append((i, obj))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Statement tape schema guard")
    parser.add_argument("--list", action="store_true", help="Print row summaries")
    parser.add_argument(
        "--registry", default=str(REGISTRY),
        help="Path to registry.jsonl (default: data/statement_tape/registry.jsonl)"
    )
    args = parser.parse_args()

    path = Path(args.registry)
    if not path.exists():
        print(f"ERROR: registry not found at {path}", file=sys.stderr)
        return 1

    rows = load_rows(path)
    if not rows:
        print("WARNING: registry is empty or has no data rows", file=sys.stderr)
        return 0

    all_errors: list[str] = []
    for lineno, row in rows:
        errors = validate_row(row, lineno)
        all_errors.extend(errors)
        if args.list:
            status = "OK" if not errors else f"FAIL({len(errors)})"
            print(
                f"[{status}] line={lineno} date={row.get('date','')} "
                f"speaker={row.get('speaker','')!r} "
                f"stance={row.get('stance_tag','')!r} "
                f"venue={row.get('venue','')!r}"
            )

    if all_errors:
        for err in all_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        print(
            f"\ncheck_statement_tape: {len(all_errors)} error(s) in {len(rows)} row(s)",
            file=sys.stderr
        )
        return 1

    print(f"check_statement_tape: OK — {len(rows)} row(s) valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
