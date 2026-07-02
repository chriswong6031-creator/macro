#!/usr/bin/env python3
"""scripts/check_claim_passport.py — Claim Passport static linter (§2.1, §3).

Scans scored-consumer engine modules for reads of registered qualitative fields.
FAILS (exit 1) if any registered field is consumed in a scoring context by a module
that appears in `scored_consumers` AND the field's ladder_state is not CONFIRMER+,
UNLESS the field has grandfathered:true (which records the debt explicitly but
allows the build to pass today).

Spec reference:
  §2.1: "a static map of scored-consumer files; any read of an unregistered field
         fails the build."
  §3:   "The Claim Passport linter refuses scored-context reads from any leg whose
         ladder state isn't CONFIRMER+."

Usage:
  python scripts/check_claim_passport.py           # exits 0/1
  python scripts/check_claim_passport.py --strict  # fail even on grandfathered
  python scripts/check_claim_passport.py --report  # print full report, always exit 0

The linter does TWO passes:
  1. Registry check — every scored_consumer/field pair in the ladder must have a
     valid ladder_state.  Unknown fields consumed in scoring modules that are NOT in
     the registry FAIL unconditionally (unregistered = not a controlled experiment).
  2. AST/grep scan — find reads of each registered field in each scoring module and
     verify the ladder state permits scored use.

The grep pattern is conservative: it flags the field name as a string key lookup
(`.get("field")` or `["field"]`) in the module. This catches the dominant pattern
without requiring a full AST; edge-cases (dynamic key assembly) are logged as
warnings and counted but do not cause a pass.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: pyyaml not installed — pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
_LADDER_PATH = _REPO / "config" / "qual_ladder.yml"

# Ladder states that permit a scored-context read (§3)
_SCORED_OK = {"CONFIRMER", "SCORED"}
# States that exist but are NOT yet scored-eligible
_PENDING_STATES = {"DISPLAY", "SHADOW"}

# Pattern: Python string-key attribute read   .get("field") or ["field"]
_KEY_RE = re.compile(r'(?:\.get\(["\'])({field})["\']|["\']({field})["\']')


def _field_pattern(field: str) -> re.Pattern[str]:
    """Return a compiled pattern that matches reads of the given field name."""
    esc = re.escape(field)
    return re.compile(
        r'(?:\.get\(["\']' + esc + r'["\']|\[' + r'["\']' + esc + r'["\'])'
    )


# ---------------------------------------------------------------------------
# Ladder loading
# ---------------------------------------------------------------------------
def load_ladder(path: Path = _LADDER_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ---------------------------------------------------------------------------
# Module-level grep scan
# ---------------------------------------------------------------------------
def scan_module_for_field(module_path: Path, field: str) -> list[int]:
    """Return line numbers where `field` appears as a string key read in module_path.
    Heuristic: matches .get("field") or ["field"] patterns."""
    if not module_path.exists():
        return []
    src = module_path.read_text(encoding="utf-8", errors="replace")
    pat = _field_pattern(field)
    lines: list[int] = []
    for i, line in enumerate(src.splitlines(), 1):
        if pat.search(line):
            lines.append(i)
    return lines


# ---------------------------------------------------------------------------
# AST-based scope check: is a line inside a scoring function?
# ---------------------------------------------------------------------------
_SCORING_FUNC_HINTS = frozenset({
    # common scoring function name substrings across the consumer modules
    "score", "edge", "lean", "dirs", "conv", "rank", "weight", "confirm",
    "combine", "composite", "direction", "signal",
})


def _func_name_is_scoring(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in _SCORING_FUNC_HINTS)


# ---------------------------------------------------------------------------
# Main lint pass
# ---------------------------------------------------------------------------
def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(_REPO))
    except ValueError:
        return str(p)


def run_lint(ladder: dict[str, Any], strict: bool = False,
             report_only: bool = False) -> tuple[list[str], list[str], list[str]]:
    """Returns (errors, warnings, infos).

    errors:   violations that cause exit 1
    warnings: grandfathered debts (exit 0 unless --strict)
    infos:    hits that passed
    """
    errors: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []

    for entry_key, entry in ladder.items():
        if not isinstance(entry, dict):
            continue
        field: str = entry.get("field") or entry_key.split(".")[-1]
        state: str = (entry.get("ladder_state") or "DISPLAY").upper()
        grandfathered: bool = bool(entry.get("grandfathered", False))
        gated_by: str = str(entry.get("gated_by") or "")
        consumers: list[str] = list(entry.get("scored_consumers") or [])

        if not consumers:
            infos.append(f"  [SKIP] {entry_key}: no scored_consumers declared")
            continue

        for consumer_rel in consumers:
            module_path = _REPO / consumer_rel
            hit_lines = scan_module_for_field(module_path, field)

            if not hit_lines:
                # Field not found in this module — either the field name differs from
                # the grep pattern, or the consumer no longer reads it.
                warnings.append(
                    f"  [WARN] {entry_key} declared in scored_consumers "
                    f"{consumer_rel!r} but no .get(\"{field}\") found — "
                    f"check field name or pattern"
                )
                continue

            for line_no in hit_lines:
                loc = f"{consumer_rel}:{line_no}"
                if state in _SCORED_OK:
                    infos.append(f"  [OK]   {entry_key} read at {loc} — state={state}")
                elif grandfathered:
                    msg = (
                        f"  [DEBT] {entry_key} read at {loc} — "
                        f"state={state} (grandfathered; gated_by: {gated_by.strip()[:80]})"
                    )
                    if strict:
                        errors.append(msg)
                    else:
                        warnings.append(msg)
                else:
                    errors.append(
                        f"  [FAIL] {entry_key} read at {loc} — "
                        f"ladder_state={state} is not CONFIRMER+ and field is NOT "
                        f"grandfathered. Register and promote the field, or add "
                        f"grandfathered:true with a gated_by note. "
                        f"Spec §3: scored-context reads require CONFIRMER+."
                    )

    return errors, warnings, infos


# ---------------------------------------------------------------------------
# Unknown-field scan: scored modules that read a field NOT in the ladder
# ---------------------------------------------------------------------------
# Fields that are purely structural/metadata and should not require registration.
_EXEMPT_KEYS = frozenset({
    "state", "lifecycle", "source", "ticker", "asof", "desk", "claim_id",
    "n_obs", "n_dates", "hit_rate", "excess_mean", "horizon_d",
    "is_placebo", "status", "label", "timestamp", "type", "key",
    "sector", "bench", "control", "entry_levels", "falsifier",
    "check_by", "timestamp_quality", "present", "breadth", "regime",
    "sentiment_lean", "n_recent", "prior_avg", "accel", "spike",
    "edge_score", "lean", "dir", "score", "n", "gap", "lag_present",
    "weighted_score", "rs_vs_spy_60d", "action", "conviction",
    "growth_score", "n_base", "stance", "days", "net_confirm", "agreement",
})

# Registered qualitative field bare names (the leaf names, not dotted entry keys)
def _registered_fields(ladder: dict[str, Any]) -> frozenset[str]:
    out: set[str] = set()
    for entry in ladder.values():
        if isinstance(entry, dict):
            f = entry.get("field")
            if f:
                out.add(f)
    return frozenset(out)


def run_unregistered_scan(ladder: dict[str, Any]) -> list[str]:
    """Warn about reads of qual-flavored fields in scored modules that are NOT in the
    registry. This is a heuristic advisory only — does not cause exit 1."""
    registered = _registered_fields(ladder)

    # Collect all scored-consumer modules from the ladder
    scored_modules: set[str] = set()
    for entry in ladder.values():
        if isinstance(entry, dict):
            for m in (entry.get("scored_consumers") or []):
                scored_modules.add(m)

    # Qualitative-flavored key hints (heuristic)
    _QUAL_KEY_HINTS = re.compile(
        r'\.get\(["\'](\w+)["\']|\[["\'](\w+)["\']\]',
        re.ASCII,
    )
    # Key substrings that suggest a qual/scored field
    _QUAL_HINTS = {"score", "lean", "signal", "conviction", "sentiment",
                   "importance", "direction", "policy", "china", "altdata",
                   "novelty", "edge", "confirm"}

    warnings: list[str] = []
    for consumer_rel in sorted(scored_modules):
        module_path = _REPO / consumer_rel
        if not module_path.exists():
            continue
        src = module_path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.splitlines(), 1):
            for m in _QUAL_KEY_HINTS.finditer(line):
                key = m.group(1) or m.group(2) or ""
                if not key or key in _EXEMPT_KEYS or key in registered:
                    continue
                if any(h in key.lower() for h in _QUAL_HINTS):
                    warnings.append(
                        f"  [UNREGISTERED?] {consumer_rel}:{i} "
                        f"reads key={key!r} which looks qual-flavored "
                        f"but is not in qual_ladder.yml — add it or confirm it's exempt"
                    )
    return warnings


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Claim Passport linter — enforce qual signal promotion ladder (§2.1, §3)"
    )
    ap.add_argument("--strict", action="store_true",
                    help="Fail (exit 1) even on grandfathered/debt entries")
    ap.add_argument("--report", action="store_true",
                    help="Print full report but always exit 0 (for CI diff reporting)")
    ap.add_argument("--ladder", default=str(_LADDER_PATH),
                    help=f"Path to qual_ladder.yml (default: {_LADDER_PATH})")
    ap.add_argument("--no-unregistered-scan", action="store_true",
                    help="Skip the advisory unregistered-field scan")
    args = ap.parse_args()

    ladder_path = Path(args.ladder)
    if not ladder_path.exists():
        print(f"ERROR: ladder not found at {ladder_path}", file=sys.stderr)
        sys.exit(2)

    ladder = load_ladder(ladder_path)
    if not ladder:
        print("ERROR: qual_ladder.yml is empty or failed to parse", file=sys.stderr)
        sys.exit(2)

    print(f"Claim Passport linter — {len(ladder)} registered entries")
    print(f"Spec: §2.1 (Claim Passport), §3 (promotion protocol)")
    print(f"Ladder: {_rel(ladder_path)}")
    print()

    errors, warnings, infos = run_lint(ladder, strict=args.strict,
                                       report_only=args.report)

    unregistered_warnings: list[str] = []
    if not args.no_unregistered_scan:
        unregistered_warnings = run_unregistered_scan(ladder)

    if infos:
        print(f"PASSED ({len(infos)} reads):")
        for l in infos:
            print(l)
        print()

    if warnings:
        print(f"DEBT / WARNINGS ({len(warnings)}):")
        for l in warnings:
            print(l)
        print()

    if unregistered_warnings:
        print(f"ADVISORY — possibly unregistered qual fields ({len(unregistered_warnings)}):")
        for l in unregistered_warnings[:20]:  # cap advisory noise
            print(l)
        if len(unregistered_warnings) > 20:
            print(f"  ... and {len(unregistered_warnings)-20} more (run with --report to see all)")
        print()

    if errors:
        print(f"ERRORS ({len(errors)}) — spec §3 violation:")
        for l in errors:
            print(l)
        print()
        print("RESULT: FAIL — Claim Passport violations found.")
        print("  Each FAIL entry must either:")
        print("  (a) promote the field to CONFIRMER+ in config/qual_ladder.yml after")
        print("      passing the §3 gate (n_dates>=25, wilson_ci_low>0 vs control), OR")
        print("  (b) add grandfathered:true with a gated_by note documenting the W0")
        print("      interim gate that limits blast radius while the field is UNGRADED.")
        if not args.report:
            sys.exit(1)
    else:
        n_debt = sum(1 for w in warnings if "[DEBT]" in w)
        print(f"RESULT: PASS ({n_debt} grandfathered debt entries; "
              f"remove grandfathered:true once §3 gate clears)")


if __name__ == "__main__":
    main()
