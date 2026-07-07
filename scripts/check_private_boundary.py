"""FB-R13 — Mastermind Feedback Contract privacy-boundary guard.

Enforces two invariants for the Mastermind → Neural Web reverse-feedback
contract (research/MASTERMIND_FEEDBACK_CONTRACT_PROGRAM.md):

  (a) ``data/private/`` and ``data/operator/`` are gitignored (ignore rail).
  (b) Committed feedback artifacts carry only counts — no tickers, fill/position/
      decision IDs, host paths, dollar amounts, or secret env-var patterns.

Rules cited: FB-R12 (data/private/ rail), FB-R13 (CI guard).

Scanned artifacts (b)
---------------------
Feedback-counts-only artifacts (full key scan):
  site/mastermind/nw_feedback.json  (and any nw_feedback*.json)
  data/governance/mastermind_feedback_summary.json
  data/governance/operator_grading.json
  data/governance/operator_exposure_summary.json
  data/governance/grading_closure.json

``site/mastermind/mastermind_snapshot.json`` is EXEMPT from the private-key scan
(FB-R1: the paper book publishes tickers/weights by design) but is NOT exempt
from host-path and secret-pattern scans.

All committed ``data/governance/*.json`` and ``site/mastermind/*.json`` are also
scanned for host-path patterns (``/Users/`` or ``/home/``) in string values.

Exit codes
----------
0 : No violations found (clean).
1 : One or more violations found.

Usage
-----
  python scripts/check_private_boundary.py              # normal run
  python scripts/check_private_boundary.py --root /path/to/repo
  python scripts/check_private_boundary.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Forbidden private field keys in counts-only artifacts (FB-R8)
# ---------------------------------------------------------------------------
_FORBIDDEN_KEYS: frozenset[str] = frozenset([
    "ticker",
    "tickers",
    "fill_id",
    "position_uid",
    "decision_id",
    "rejection_id",
    "shares",
    "notional",
    "avg_cost",
    "account",
    "broker",
    "venue",
])

# Regex patterns for forbidden string values
# Host paths: absolute /Users/ or /home/ in string values
_RE_HOST_PATH = re.compile(r"/(?:Users|home)/")
# Dollar amounts: $12,345 or $1,234,567
_RE_DOLLAR_AMOUNT = re.compile(r"\$[\d,]{3,}")
# Secret env-var patterns: MASTERMIND_TOKEN, MASTERMIND_API_KEY, etc.
_RE_SECRET_ENV = re.compile(r"\bMASTERMIND_[A-Z_]+\b")

# ---------------------------------------------------------------------------
# Artifacts subject to the private key scan (FB-R13 §b)
# ---------------------------------------------------------------------------
# These paths are relative to the repo root.  Globs are expanded at scan time.
_KEY_SCAN_GLOBS: tuple[str, ...] = (
    "site/mastermind/nw_feedback*.json",
    "data/governance/mastermind_feedback_summary.json",
    "data/governance/operator_grading.json",
    "data/governance/operator_exposure_summary.json",
    "data/governance/grading_closure.json",
)

# Artifacts exempt from the private-key scan but NOT from host-path/secret scans.
_KEY_SCAN_EXEMPT: frozenset[str] = frozenset([
    "site/mastermind/mastermind_snapshot.json",
])

# Broader host-path scan: all committed *.json in these dirs
_HOST_PATH_SCAN_GLOBS: tuple[str, ...] = (
    "data/governance/*.json",
    "site/mastermind/*.json",
)


# ---------------------------------------------------------------------------
# JSON walker — recursively yield (key_path_str, key, value) for every node
# ---------------------------------------------------------------------------
def _walk_json(obj: Any, path: str = "") -> list[tuple[str, str | None, Any]]:
    """Recursively yield (json_path, key_or_None, value) tuples.

    For dicts: yields (path.key, key, value) for each k/v pair.
    For lists: yields (path[i], None, element) for each element.
    For scalars: yields (path, None, scalar) at the leaf.
    """
    result: list[tuple[str, str | None, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}" if path else k
            result.append((child_path, k, v))
            result.extend(_walk_json(v, child_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            child_path = f"{path}[{i}]"
            result.extend(_walk_json(item, child_path))
    return result


# ---------------------------------------------------------------------------
# Single-artifact scan
# ---------------------------------------------------------------------------
def _scan_artifact(
    rel_path: str,
    source_text: str,
    *,
    check_keys: bool,
    check_host_path: bool = True,
    check_secret_env: bool = True,
    check_dollar_amount: bool = True,
) -> list[dict]:
    """Scan one JSON artifact for violations.

    Parameters
    ----------
    rel_path             : Repo-relative path (used in violation messages).
    source_text          : Raw JSON text.
    check_keys           : Whether to scan for forbidden field names (FB-R8).
    check_host_path      : Whether to scan for host paths in string values.
    check_secret_env     : Whether to scan for MASTERMIND_<NAME> patterns.
    check_dollar_amount  : Whether to scan for dollar-amount patterns.

    Returns
    -------
    List of violation dicts:
      {artifact, json_path, violation_type, detail}
    """
    violations: list[dict] = []

    try:
        obj = json.loads(source_text)
    except json.JSONDecodeError as exc:
        violations.append({
            "artifact": rel_path,
            "json_path": "<root>",
            "violation_type": "json_parse_error",
            "detail": str(exc),
        })
        return violations

    for json_path, key, value in _walk_json(obj):
        # (1) Forbidden key names in counts-only artifacts (scan b)
        if check_keys and key is not None:
            key_lower = key.lower()
            if key_lower in _FORBIDDEN_KEYS:
                violations.append({
                    "artifact": rel_path,
                    "json_path": json_path,
                    "violation_type": "forbidden_key",
                    "detail": (
                        f"Key {key!r} is a private identifier forbidden in "
                        f"counts-only feedback artifacts (FB-R8)."
                    ),
                })

        # (2) String value checks
        if isinstance(value, str):
            if check_host_path and _RE_HOST_PATH.search(value):
                violations.append({
                    "artifact": rel_path,
                    "json_path": json_path,
                    "violation_type": "host_path_in_value",
                    "detail": (
                        f"String value contains an absolute host path "
                        f"(/Users/ or /home/): {value[:120]!r}"
                    ),
                })
            if check_dollar_amount and _RE_DOLLAR_AMOUNT.search(value):
                violations.append({
                    "artifact": rel_path,
                    "json_path": json_path,
                    "violation_type": "dollar_amount_in_value",
                    "detail": (
                        f"String value matches dollar-amount pattern "
                        f"($NNN,...): {value[:120]!r}"
                    ),
                })
            if check_secret_env and _RE_SECRET_ENV.search(value):
                violations.append({
                    "artifact": rel_path,
                    "json_path": json_path,
                    "violation_type": "secret_env_pattern",
                    "detail": (
                        f"String value matches secret env-var pattern "
                        f"(MASTERMIND_<NAME>): {value[:120]!r}"
                    ),
                })

    return violations


# ---------------------------------------------------------------------------
# Ignore-rail check
# ---------------------------------------------------------------------------
def _check_ignore_rail(root: Path) -> list[dict]:
    """Verify that data/private/ and data/operator/ are gitignored.

    Uses ``git check-ignore -q <path>``; exit 0 means ignored.

    Returns list of violation dicts (empty = clean).
    """
    violations: list[dict] = []
    probe_pairs = [
        ("data/private/__probe__", "data/private/"),
        ("data/operator/__probe__", "data/operator/"),
    ]
    for probe_path, label in probe_pairs:
        try:
            result = subprocess.run(
                ["git", "check-ignore", "-q", probe_path],
                cwd=str(root),
                capture_output=True,
            )
            if result.returncode != 0:
                violations.append({
                    "artifact": ".gitignore",
                    "json_path": None,
                    "violation_type": "missing_ignore_rail",
                    "detail": (
                        f"{label!r} is NOT gitignored. "
                        f"The nightly blanket 'git add data/' would stage any file "
                        f"written there. Add '{label}' to .gitignore (FB-R12)."
                    ),
                })
        except (FileNotFoundError, OSError) as exc:
            violations.append({
                "artifact": ".gitignore",
                "json_path": None,
                "violation_type": "git_check_ignore_error",
                "detail": (
                    f"Could not run 'git check-ignore' for {probe_path}: {exc}"
                ),
            })
    return violations


# ---------------------------------------------------------------------------
# Full scan
# ---------------------------------------------------------------------------
def scan(
    root: Path,
    extra_artifacts: dict[str, str] | None = None,
    skip_ignore_rail: bool = False,
) -> list[dict]:
    """Run the full privacy-boundary scan.

    Parameters
    ----------
    root             : Repo root.
    extra_artifacts  : Optional dict of {repo-relative-path: json_text} for
                       synthetic fixtures (used in selftest).  When provided,
                       ONLY these artifacts are scanned (no disk traversal).
    skip_ignore_rail : When True, skip the git check-ignore step
                       (used in selftest contexts where git is not available
                       over a tempdir fixture).

    Returns
    -------
    List of violation dicts.
    """
    violations: list[dict] = []

    # ── Ignore rail ───────────────────────────────────────────────────────────
    if not skip_ignore_rail and extra_artifacts is None:
        violations.extend(_check_ignore_rail(root))

    # ── Artifact scans ───────────────────────────────────────────────────────
    if extra_artifacts is not None:
        # Selftest path: only scan the provided synthetic fixtures.
        for rel_path, text in extra_artifacts.items():
            is_exempt = rel_path in _KEY_SCAN_EXEMPT
            # Exempt artifacts (mastermind_snapshot.json) skip the counts-only
            # scan (keys + dollar amounts + secret env) but remain subject to
            # the broader host-path scan (scan c).
            violations.extend(
                _scan_artifact(
                    rel_path,
                    text,
                    check_keys=not is_exempt,
                    check_dollar_amount=not is_exempt,
                    check_secret_env=not is_exempt,
                    check_host_path=True,
                )
            )
        return violations

    # Normal path: collect artifacts from disk.
    # (a) Key-scan artifacts (counts-only feedback artifacts)
    key_scan_paths: set[str] = set()
    for glob in _KEY_SCAN_GLOBS:
        for p in sorted(root.glob(glob)):
            if p.is_file():
                key_scan_paths.add(str(p.relative_to(root)))

    # (b) Host-path scan artifacts (superset — scan c, broader)
    host_scan_paths: set[str] = set()
    for glob in _HOST_PATH_SCAN_GLOBS:
        for p in sorted(root.glob(glob)):
            if p.is_file():
                host_scan_paths.add(str(p.relative_to(root)))

    all_paths = key_scan_paths | host_scan_paths

    for rel_path in sorted(all_paths):
        rel_path_norm = rel_path.replace("\\", "/")
        is_exempt = rel_path_norm in _KEY_SCAN_EXEMPT
        is_key_scan = rel_path_norm in key_scan_paths and not is_exempt

        # Exempt artifacts (mastermind_snapshot.json) are subject to host-path
        # scan only (scan c).  Non-exempt feedback artifacts run the full scan.
        try:
            text = (root / rel_path).read_text(encoding="utf-8")
        except OSError:
            continue

        violations.extend(
            _scan_artifact(
                rel_path_norm,
                text,
                check_keys=is_key_scan,
                check_dollar_amount=is_key_scan,
                check_secret_env=is_key_scan,
                check_host_path=True,
            )
        )

    return violations


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------
def _run_selftest(root: Path) -> int:
    """Prove the guard fires on planted violations and is silent on clean code."""
    all_passed = True

    # ── Test 1: ticker key in a feedback artifact → forbidden_key violation ──
    fixture_ticker = json.dumps({
        "schema": "mastermind_nw_feedback.v1",
        "generated_at": "2026-07-06T12:00:00+00:00",
        "ticker": "AAPL",
        "run_count": 42,
    })
    v1 = scan(
        root,
        extra_artifacts={"site/mastermind/nw_feedback.json": fixture_ticker},
        skip_ignore_rail=True,
    )
    found_ticker = any(d["violation_type"] == "forbidden_key" for d in v1)
    status = "PASS" if found_ticker else "FAIL"
    if not found_ticker:
        all_passed = False
    print(f"  selftest [{status}] ticker key in feedback artifact → forbidden_key")

    # ── Test 2: fill_id key → forbidden_key violation ────────────────────────
    fixture_fill_id = json.dumps({
        "schema": "operator_grading.v1",
        "fill_id": "abc123",
        "run_count": 5,
    })
    v2 = scan(
        root,
        extra_artifacts={"data/governance/operator_grading.json": fixture_fill_id},
        skip_ignore_rail=True,
    )
    found_fill_id = any(d["violation_type"] == "forbidden_key" for d in v2)
    status = "PASS" if found_fill_id else "FAIL"
    if not found_fill_id:
        all_passed = False
    print(f"  selftest [{status}] fill_id key in governance artifact → forbidden_key")

    # ── Test 3: /Users/ path in string value → host_path_in_value ────────────
    fixture_host = json.dumps({
        "schema": "operator_grading.v1",
        "ledger_path": "/Users/chriswong/Documents/Cluade/Macro Dashboard/data/operator/action_ledger.jsonl",
        "run_count": 0,
    })
    v3 = scan(
        root,
        extra_artifacts={"data/governance/operator_grading.json": fixture_host},
        skip_ignore_rail=True,
    )
    found_host = any(d["violation_type"] == "host_path_in_value" for d in v3)
    status = "PASS" if found_host else "FAIL"
    if not found_host:
        all_passed = False
    print(f"  selftest [{status}] /Users/ path in string value → host_path_in_value")

    # ── Test 4: $12,345 dollar amount → dollar_amount_in_value ───────────────
    fixture_dollar = json.dumps({
        "schema": "operator_exposure_summary.v1",
        "note": "Total NAV: $12,345 unrealized",
        "run_count": 10,
    })
    v4 = scan(
        root,
        extra_artifacts={"data/governance/operator_exposure_summary.json": fixture_dollar},
        skip_ignore_rail=True,
    )
    found_dollar = any(d["violation_type"] == "dollar_amount_in_value" for d in v4)
    status = "PASS" if found_dollar else "FAIL"
    if not found_dollar:
        all_passed = False
    print(f"  selftest [{status}] dollar-amount string → dollar_amount_in_value")

    # ── Test 5: MASTERMIND_TOKEN in string value → secret_env_pattern ────────
    fixture_secret = json.dumps({
        "schema": "grading_closure.v1",
        "debug_token": "MASTERMIND_TOKEN=abc123xyz",
        "run_count": 0,
    })
    v5 = scan(
        root,
        extra_artifacts={"data/governance/grading_closure.json": fixture_secret},
        skip_ignore_rail=True,
    )
    found_secret = any(d["violation_type"] == "secret_env_pattern" for d in v5)
    status = "PASS" if found_secret else "FAIL"
    if not found_secret:
        all_passed = False
    print(f"  selftest [{status}] MASTERMIND_<NAME> in string → secret_env_pattern")

    # ── Test 6: clean counts-only fixture → no violations ─────────────────────
    fixture_clean = json.dumps({
        "schema": "mastermind_nw_feedback.v1",
        "generated_at": "2026-07-06T12:00:00+00:00",
        "state": "present",
        "window_days": 30,
        "n_runs": 42,
        "n_context_present": 35,
        "n_context_absent": 7,
        "context_seen_rate": 0.833,
    })
    v6 = scan(
        root,
        extra_artifacts={"site/mastermind/nw_feedback.json": fixture_clean},
        skip_ignore_rail=True,
    )
    clean_ok = len(v6) == 0
    status = "PASS" if clean_ok else "FAIL"
    if not clean_ok:
        all_passed = False
        for d in v6:
            print(f"    unexpected violation: {d}")
    print(f"  selftest [{status}] counts-only clean fixture → no violations")

    # ── Test 7: mastermind_snapshot.json exempt from key scan ─────────────────
    # Snapshot may contain tickers by design (FB-R1) — exempt from key scan.
    # It must NOT be exempt from host-path scan.
    fixture_snap_tickers = json.dumps({
        "schema": "mastermind_snapshot.v1",
        "ticker": "NVDA",
        "weight": 0.15,
        "note": "position published by design",
    })
    v7a = scan(
        root,
        extra_artifacts={"site/mastermind/mastermind_snapshot.json": fixture_snap_tickers},
        skip_ignore_rail=True,
    )
    exempt_ok = not any(d["violation_type"] == "forbidden_key" for d in v7a)
    status = "PASS" if exempt_ok else "FAIL"
    if not exempt_ok:
        all_passed = False
    print(f"  selftest [{status}] mastermind_snapshot.json ticker exempt from key scan")

    # Snapshot is NOT exempt from host-path scan
    fixture_snap_host = json.dumps({
        "schema": "mastermind_snapshot.v1",
        "debug_path": "/Users/chriswong/Documents/Macro/run.log",
    })
    v7b = scan(
        root,
        extra_artifacts={"site/mastermind/mastermind_snapshot.json": fixture_snap_host},
        skip_ignore_rail=True,
    )
    snap_host_caught = any(d["violation_type"] == "host_path_in_value" for d in v7b)
    status = "PASS" if snap_host_caught else "FAIL"
    if not snap_host_caught:
        all_passed = False
    print(f"  selftest [{status}] mastermind_snapshot.json host-path NOT exempt → caught")

    print()
    if all_passed:
        print("selftest PASSED — all synthetic cases handled correctly")
        return 0
    else:
        print("selftest FAILED — one or more cases not caught")
        return 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--root", type=Path, default=ROOT,
        help="Repo root (default: parent of scripts/)"
    )
    ap.add_argument(
        "--selftest", action="store_true",
        help="Run selftest with synthetic fixtures; exit 0 on pass, 1 on fail"
    )
    args = ap.parse_args()

    root = args.root.resolve()

    if args.selftest:
        print("Running privacy-boundary guard selftest ...")
        return _run_selftest(root)

    violations = scan(root)

    if not violations:
        print(
            "check_private_boundary: OK — "
            "ignore rails present; no private fields in committed artifacts."
        )
        return 0

    for v in violations:
        jp = f":{v['json_path']}" if v.get("json_path") else ""
        print(
            f"  [VIOLATION] {v['artifact']}{jp} — "
            f"[{v['violation_type']}] {v['detail']}",
            file=sys.stderr,
        )

    print(
        f"\n::error::check_private_boundary: {len(violations)} privacy-boundary "
        f"violation(s) found. Committed feedback artifacts must be counts-only — "
        f"no tickers, fill/position/decision IDs, host paths, dollar amounts, or "
        f"secret env-var patterns (FB-R8/FB-R13).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
