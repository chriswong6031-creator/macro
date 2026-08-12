"""
scripts/check_qledger_metric_validity.py — Universal Scoreboard metric-validity gate.

Audits the qledger claim/grade corpus for the three ways a reader can compute an
impressive-looking number that does not mean what it appears to mean. The
invariants, their evidence, and why each is silent are documented in
:mod:`engine.qledger_validity`.

WARN-TIER BY DEFAULT — AND WHY (deliberate, not an oversight)
-------------------------------------------------------------
The findings this gate emits are PRE-EXISTING CONDITIONS of the corpus, not
regressions introduced by any one PR. On the 2026-08-12 store it reports on the
majority of families the moment it is wired. Shipping it as a hard gate would
red main on day one for a property no PR author caused, which is how a guard
gets disabled instead of obeyed (`DNR` precedent: a gate that fires fleet-wide
is routed around, not satisfied).

So: default exit 0 with ``::warning`` annotations. ``--strict`` exits 1 and is
the intended CI mode ONCE the emitters listed in
``research/MASTERMIND_INTELLIGENCE_OS_V1_PLAN.md`` T3 stop publishing the
invalid readings. Flipping the default is a one-word change and a deliberate act.

Annotations are emitted with a bare ``print`` and ``flush=True`` per CLAUDE.md
§"GitHub annotations must START the line" — a logger would prefix the line and
GitHub would silently drop it.

Usage
-----
  python scripts/check_qledger_metric_validity.py [--root PATH] [--strict]
  python scripts/check_qledger_metric_validity.py --selftest

Options
-------
  --root PATH   Repo root holding data/qledger/{claims,grades}.jsonl
                (default: parent of scripts/).
  --strict      Exit 1 when any finding has severity 'invalid'.
  --json        Emit a JSON object to stdout instead of annotations. ALWAYS an
                object, never a bare list: {store_absent, missing, claims,
                grades, findings}. When the store is absent, `findings` is null
                rather than [] — an empty list would render "could not look" as
                "looked and clean" (standards §9.2).
  --selftest    Inject synthetic corpora proving the auditor catches each
                invariant AND stays silent on a clean corpus. Exits 0 if every
                expected finding is caught, 1 otherwise.
                Precedent: scripts/check_synapse_registry.py --selftest.

An ABSENT store is not a failure: the qledger store is gitignored on some
checkouts and absent in sparse agent worktrees. A missing file exits 0 with a
notice, because "I could not look" must never render as "I looked and it was
clean" (CLAUDE.md §Epistemics; nulls are printed, not hidden).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.qledger_validity import (  # noqa: E402
    SEVERITY_INVALID,
    Finding,
    audit,
)

CLAIMS_REL = ("data", "qledger", "claims.jsonl")
GRADES_REL = ("data", "qledger", "grades.jsonl")


def _read_jsonl(path: Path) -> list[dict]:
    """Read a qledger JSONL store, skipping '#' schema-comment lines.

    Several ledger stores in this repo lead with '#' comment lines documenting
    the row schema, so a naive json.loads-per-line raises on line 1.
    """
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _json_payload(
    findings: list[Finding] | None,
    *,
    store_absent: bool,
    n_claims: int | None = None,
    n_grades: int | None = None,
    missing: list[str] | None = None,
) -> str:
    """The --json contract: ALWAYS an object, never a bare list.

    `store_absent` is a first-class field rather than an empty findings list,
    because an empty list would render "I could not look" as "I looked and it
    was clean" — the exact substitution research/MASTERMIND_EVALUATION_STANDARDS.md
    §9.2 forbids. A consumer must be able to tell the two apart without parsing
    prose, so `findings` is null (not []) when nothing was audited.
    """
    return json.dumps(
        {
            "store_absent": store_absent,
            "missing": missing or [],
            "claims": n_claims,
            "grades": n_grades,
            "findings": None
            if findings is None
            else [
                {
                    "code": f.code,
                    "family": f.family,
                    "severity": f.severity,
                    "detail": f.detail,
                }
                for f in findings
            ],
        },
        indent=2,
    )


def _emit(findings: list[Finding], as_json: bool, n_claims: int, n_grades: int) -> None:
    if as_json:
        print(
            _json_payload(
                findings, store_absent=False, n_claims=n_claims, n_grades=n_grades
            ),
            flush=True,
        )
        return
    for finding in findings:
        level = "error" if finding.severity == SEVERITY_INVALID else "warning"
        # Bare print, line-start, flushed — see module docstring.
        print(
            f"::{level} title=qledger-metric-validity::"
            f"[{finding.code}] {finding.family}: {finding.detail}",
            flush=True,
        )


def _selftest() -> int:
    """Prove the auditor catches each invariant and stays quiet on a clean corpus."""
    checks: list[tuple[str, bool]] = []

    # V1 — a family holding both directions must refuse a pooled signed excess.
    mixed = [
        {"claim_family": "mixed", "claim_id": "a", "direction": 1, "horizon_d": 5},
        {"claim_family": "mixed", "claim_id": "b", "direction": -1, "horizon_d": 5},
    ]
    grades_v1 = [{"claim_id": "a", "horizon_d": 5}, {"claim_id": "b", "horizon_d": 5}]
    codes = {f.code for f in audit(mixed, grades_v1)}
    checks.append(("V1 mixed-direction family flagged", "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" in codes))

    # V1 negative control — a single-direction family must NOT be flagged.
    homo = [
        {"claim_family": "homo", "claim_id": "c", "direction": 1, "horizon_d": 5},
        {"claim_family": "homo", "claim_id": "d", "direction": 1, "horizon_d": 5},
    ]
    grades_homo = [{"claim_id": "c", "horizon_d": 5}, {"claim_id": "d", "horizon_d": 5}]
    codes = {f.code for f in audit(homo, grades_homo)}
    checks.append(("V1 single-direction family clean", "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" not in codes))

    # V2 — a salience-only family must refuse a hit rate.
    salience = [
        {"claim_family": "sal", "claim_id": "e", "direction": 0, "horizon_d": 5},
        {"claim_family": "sal", "claim_id": "f", "direction": 0, "horizon_d": 5},
    ]
    grades_sal = [{"claim_id": "e", "horizon_d": 5}, {"claim_id": "f", "horizon_d": 5}]
    codes = {f.code for f in audit(salience, grades_sal)}
    checks.append(("V2 salience family flagged", "HIT_RATE_ON_A_SALIENCE_FAMILY" in codes))
    checks.append(("V2 salience family may still pool excess", "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" not in codes))

    # V3 — a 63d family graded only at 5d/21d is ACCRUING, not a verdict.
    long_h = [{"claim_family": "lng", "claim_id": "g", "direction": 1, "horizon_d": 63}]
    grades_short = [{"claim_id": "g", "horizon_d": 5}, {"claim_id": "g", "horizon_d": 21}]
    codes = {f.code for f in audit(long_h, grades_short)}
    checks.append(("V3 off-horizon verdict flagged", "OFF_HORIZON_VERDICT" in codes))

    # V3 negative control — once the ruler matures, the finding clears.
    grades_matured = grades_short + [{"claim_id": "g", "horizon_d": 63}]
    codes = {f.code for f in audit(long_h, grades_matured)}
    checks.append(("V3 clears once the declared ruler matures", "OFF_HORIZON_VERDICT" not in codes))

    # Placebo rows must not decide a real family's direction profile.
    with_placebo = homo + [
        {"claim_family": "homo", "claim_id": "p", "direction": -1, "is_placebo": True, "horizon_d": 5}
    ]
    codes = {f.code for f in audit(with_placebo, grades_homo)}
    checks.append(("placebo excluded from direction profile", "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" not in codes))

    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}", flush=True)
        ok = ok and passed
    print(f"selftest: {'PASS' if ok else 'FAIL'} ({sum(1 for _, p in checks if p)}/{len(checks)})", flush=True)
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return _selftest()

    claims_path = args.root.joinpath(*CLAIMS_REL)
    grades_path = args.root.joinpath(*GRADES_REL)
    missing = [p for p in (claims_path, grades_path) if not p.exists()]
    if missing:
        # Absent store: say so out loud, exit 0. Never render as "clean".
        if args.json:
            print(
                _json_payload(None, store_absent=True, missing=[str(p) for p in missing]),
                flush=True,
            )
        else:
            for path in missing:
                print(f"::notice title=qledger-metric-validity::store absent, not audited: {path}", flush=True)
        return 0

    claims = _read_jsonl(claims_path)
    grades = _read_jsonl(grades_path)
    findings = audit(claims, grades)

    _emit(findings, args.json, len(claims), len(grades))
    invalid = [f for f in findings if f.severity == SEVERITY_INVALID]
    if not args.json:
        print(
            f"qledger metric validity: {len(claims)} claims, {len(grades)} grades, "
            f"{len(findings)} finding(s) ({len(invalid)} invalid)",
            flush=True,
        )
    if args.strict and invalid:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
