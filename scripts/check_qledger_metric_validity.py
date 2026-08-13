"""
scripts/check_qledger_metric_validity.py — Universal Scoreboard metric-validity gate.

Audits the qledger claim/grade corpus for the three ways a reader can compute an
impressive-looking number that does not mean what it appears to mean. The
invariants, their evidence, and why each is silent are documented in
:mod:`engine.qledger_validity`.

TWO MODES, AND WHY BOTH EXIST
-----------------------------
The invariants are the same in both; what differs is the QUESTION being asked.

  GATE mode (default, ``--strict``-able)
      Question: *does anything we publish actually contain an illegal reading?*
      ``reported_metrics`` is derived from ``site/qledger/track_record.json`` —
      the artifact the nightly producer wrote and every downstream consumer
      reads (engine/qledger_ui.py chips, scripts/build_measurement.py's
      reliability table, engine/experiments_registry.py's admin state line,
      engine/neuralweb/mastermind_context.py's lobe). A finding here is a DEFECT
      with an author: some emitter really did publish a pooled signed excess for
      a mixed-direction family, or a hit rate for a salience family. That is a
      legitimate merge gate, and it is satisfiable — the fix is to stop
      publishing the illegal key.

      The map is read from the PUBLISHED ARTIFACT on purpose, never by
      re-invoking the producer in-process. ``engine.qledger._aggregate`` decides
      its keys with the very predicates this gate checks, so a map derived from
      that call could not fail — the "receipt written from the same variable"
      trap. The artifact is an independent record of a prior run, so it can and
      does disagree with the current code, which is exactly what makes the gate
      able to fire.

  ADVISORY mode (``--audit-store``)
      Question: *what could a reader who reaches into the raw store get wrong?*
      ``reported_metrics`` is omitted, so the audit assumes the permissive worst
      case that any metric might be computed for any family — which is what a
      dashboard, an ad-hoc notebook, or an LLM summarising the store would do.
      Every finding it reports on the live corpus is a PROPERTY OF THE CORPUS,
      not a regression: ``radar`` will always hold both directions and
      ``us_importance_v0`` will always be salience. There is no code change that
      makes this mode green, so it must never gate a merge; ``--strict`` is
      accepted here but is a deliberate local-diagnostic choice, not a CI mode.

  (Before T3 the ONLY mode was the advisory one, which is why the guard shipped
  at warn tier with empty ci_wiring: its `--strict` was unsatisfiable by
  construction. Fixing the emitters is what made a gate possible; running the
  advisory audit as the gate is what made it impossible.)

An ABSENT input is not a pass. GATE mode with no ``site/qledger/track_record.json``
has nothing to gate, and either mode with no ``data/qledger/*.jsonl`` has no
corpus to profile against; both exit 0 with a ``::notice`` that names the missing
file. "I could not look" must never render as "I looked and it was clean"
(CLAUDE.md §Epistemics; research/MASTERMIND_EVALUATION_STANDARDS.md §9.2). Sparse
agent worktrees have neither path on disk while both are tracked in HEAD; a full
CI checkout has both.

Annotations are emitted with a bare ``print`` and ``flush=True`` per CLAUDE.md
§"GitHub annotations must START the line" — a logger would prefix the line and
GitHub would silently drop it.

Usage
-----
  python scripts/check_qledger_metric_validity.py [--root PATH] [--strict]
  python scripts/check_qledger_metric_validity.py --audit-store
  python scripts/check_qledger_metric_validity.py --selftest

Options
-------
  --root PATH     Repo root holding data/qledger/{claims,grades}.jsonl and
                  site/qledger/track_record.json (default: parent of scripts/).
  --audit-store   ADVISORY mode: permissive whole-store audit (pre-T3 behaviour).
  --strict        Exit 1 when any finding has severity 'invalid'.
  --json          Emit a JSON object to stdout instead of annotations. ALWAYS an
                  object, never a bare list: {mode, store_absent,
                  track_record_absent, missing, claims, grades, findings}. When
                  an input is absent, `findings` is null rather than [] — an
                  empty list would render "could not look" as "looked and clean".
  --selftest      Inject synthetic corpora proving the auditor catches each
                  invariant AND stays silent on a clean corpus, and that GATE
                  mode fires on a published illegal key while staying silent on
                  a published legal one. Exits 0 if every expectation holds.
                  Precedent: scripts/check_synapse_registry.py --selftest.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.qledger_validity import (  # noqa: E402
    GROUP_DESK,
    GROUP_FAMILY,
    SEVERITY_INVALID,
    Finding,
    audit,
)

CLAIMS_REL = ("data", "qledger", "claims.jsonl")
GRADES_REL = ("data", "qledger", "grades.jsonl")
TRACK_RECORD_REL = ("site", "qledger", "track_record.json")

MODE_GATE = "gate"
MODE_STORE = "store"

# The metric names whose legality the invariants speak to. `mean_abs_excess` is
# always legal (it is the magnitude reading V1 prescribes) but is collected so
# that "this group publishes something" is answerable — V3 only asks its
# question of a group that is actually read.
METRIC_KEYS = frozenset({"hit_rate", "excess_mean", "mean_abs_excess", "wilson_ci_low"})

# _duel_context is flat (no per-horizon nesting) and names its metrics with a
# horizon suffix, so it needs an explicit key map rather than a set intersection.
DUEL_KEY_MAP = {
    "challenger_excess_mean_5d": "excess_mean",
    "challenger_mean_abs_excess_5d": "mean_abs_excess",
    "wilson_ci_low_5d": "wilson_ci_low",
}


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


def derive_reported_metrics(
    track_record: dict,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Read the PUBLISHED artifact and return (by_family map, by_desk map).

    A group's entry is the union, across every horizon cell, of the metric key
    names the artifact actually carries. A group absent from the artifact
    publishes nothing and gets no entry — and therefore no finding.

    Both groupings are returned because both are published: ``by_desk`` is what
    engine/qledger_ui.py's chips read, and a desk holding two families of
    opposite direction is exactly as unpoolable as a mixed family.
    """
    by_family: dict[str, set[str]] = {}
    by_desk: dict[str, set[str]] = {}

    for section, dest in (("by_family", by_family), ("by_desk", by_desk)):
        for key, horizons in (track_record.get(section) or {}).items():
            if not isinstance(horizons, dict):
                continue
            for cell in horizons.values():
                if isinstance(cell, dict):
                    dest.setdefault(key, set()).update(set(cell) & METRIC_KEYS)

    # promotion_readiness is family-keyed and is rendered on the admin
    # Experiments tab via engine/experiments_registry.py.
    readiness = track_record.get("promotion_readiness") or {}
    if isinstance(readiness, dict):
        for key, horizons in readiness.items():
            if key.startswith("_") or not isinstance(horizons, dict):
                continue
            for cell in horizons.values():
                if isinstance(cell, dict):
                    by_family.setdefault(key, set()).update(set(cell) & METRIC_KEYS)

        duel = readiness.get("_duel_context") or {}
        if isinstance(duel, dict):
            for key, ctx in duel.items():
                if not isinstance(ctx, dict):
                    continue
                published = {
                    metric for raw, metric in DUEL_KEY_MAP.items() if raw in ctx
                }
                if published:
                    by_family.setdefault(key, set()).update(published)

    return by_family, by_desk


def _json_payload(
    findings: list[Finding] | None,
    *,
    mode: str = MODE_GATE,
    store_absent: bool,
    track_record_absent: bool = False,
    n_claims: int | None = None,
    n_grades: int | None = None,
    missing: list[str] | None = None,
) -> str:
    """The --json contract: ALWAYS an object, never a bare list.

    `store_absent` / `track_record_absent` are first-class fields rather than an
    empty findings list, because an empty list would render "I could not look" as
    "I looked and it was clean" — the exact substitution
    research/MASTERMIND_EVALUATION_STANDARDS.md §9.2 forbids. A consumer must be
    able to tell the two apart without parsing prose, so `findings` is null (not
    []) when nothing was audited.
    """
    return json.dumps(
        {
            "mode": mode,
            "store_absent": store_absent,
            "track_record_absent": track_record_absent,
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


def _emit(
    findings: list[Finding],
    as_json: bool,
    n_claims: int,
    n_grades: int,
    *,
    mode: str,
) -> None:
    if as_json:
        print(
            _json_payload(
                findings,
                mode=mode,
                store_absent=False,
                n_claims=n_claims,
                n_grades=n_grades,
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

    # ── GATE mode. The reported_metrics map is what separates a defect from a
    # hazard, so it needs both a positive and a negative control of its own:
    # the SAME corpus must fire when the illegal key is published and stay
    # silent when it is not. Without the negative control a gate that always
    # fired, or one wired to an always-empty map, would pass this selftest.
    codes = {f.code for f in audit(mixed, grades_v1, reported_metrics={"mixed": {"excess_mean"}})}
    checks.append(("GATE fires when excess_mean is published for a mixed family",
                   "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" in codes))
    codes = {f.code for f in audit(mixed, grades_v1, reported_metrics={"mixed": {"mean_abs_excess", "hit_rate"}})}
    checks.append(("GATE silent when the mixed family publishes the magnitude instead",
                   "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" not in codes))
    codes = {f.code for f in audit(salience, grades_sal, reported_metrics={"sal": {"hit_rate"}})}
    checks.append(("GATE fires when hit_rate is published for a salience family",
                   "HIT_RATE_ON_A_SALIENCE_FAMILY" in codes))
    codes = {f.code for f in audit(salience, grades_sal, reported_metrics={"sal": {"wilson_ci_low"}})}
    checks.append(("GATE fires on wilson_ci_low too (a hit rate by another name)",
                   "HIT_RATE_ON_A_SALIENCE_FAMILY" in codes))
    codes = {f.code for f in audit(salience, grades_sal, reported_metrics={"sal": {"excess_mean"}})}
    checks.append(("GATE silent when the salience family publishes no hit rate",
                   "HIT_RATE_ON_A_SALIENCE_FAMILY" not in codes))

    # Desk grouping must be auditable too: by_desk is published alongside
    # by_family and a desk can be mixed-direction even when no single family is.
    two_family_desk = [
        {"claim_family": "up", "desk": "d1", "claim_id": "h", "direction": 1, "horizon_d": 5},
        {"claim_family": "down", "desk": "d1", "claim_id": "i", "direction": -1, "horizon_d": 5},
    ]
    grades_desk = [{"claim_id": "h", "horizon_d": 5}, {"claim_id": "i", "horizon_d": 5}]
    codes = {f.code for f in audit(two_family_desk, grades_desk, group_by=GROUP_FAMILY,
                                   reported_metrics={"up": {"excess_mean"}, "down": {"excess_mean"}})}
    checks.append(("family grouping sees two clean single-direction families",
                   "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" not in codes))
    codes = {f.code for f in audit(two_family_desk, grades_desk, group_by=GROUP_DESK,
                                   reported_metrics={"d1": {"excess_mean"}})}
    checks.append(("desk grouping catches the mix the family grouping cannot see",
                   "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" in codes))

    # The artifact reader must actually find the published keys, or GATE mode
    # would gate an empty map and be green for the wrong reason.
    fam_map, desk_map = derive_reported_metrics({
        "by_family": {"radar": {"5": {"n_obs": 3, "excess_mean": 0.1}}},
        "by_desk": {"radar": {"5": {"n_obs": 3, "hit_rate": 0.5}}},
        "promotion_readiness": {
            "sal": {"5": {"hit_rate": None, "n_dates": 2}},
            "_duel_context": {"radar": {"challenger_excess_mean_5d": 0.1}},
        },
    })
    checks.append(("artifact reader finds by_family excess_mean", fam_map.get("radar") == {"excess_mean"}))
    checks.append(("artifact reader finds by_desk hit_rate", desk_map.get("radar") == {"hit_rate"}))
    checks.append(("artifact reader finds promotion_readiness hit_rate", fam_map.get("sal") == {"hit_rate"}))
    checks.append((
        "artifact reader ignores a group the artifact does not publish",
        "never_published" not in fam_map,
    ))

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
    parser.add_argument(
        "--audit-store",
        action="store_true",
        help="ADVISORY mode: permissive whole-store audit (never a CI gate).",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return _selftest()

    mode = MODE_STORE if args.audit_store else MODE_GATE

    claims_path = args.root.joinpath(*CLAIMS_REL)
    grades_path = args.root.joinpath(*GRADES_REL)
    track_path = args.root.joinpath(*TRACK_RECORD_REL)

    needed = [claims_path, grades_path]
    if mode == MODE_GATE:
        needed.append(track_path)
    missing = [p for p in needed if not p.exists()]
    if missing:
        # Absent input: say so out loud, exit 0. Never render as "clean".
        if args.json:
            print(
                _json_payload(
                    None,
                    mode=mode,
                    store_absent=not (claims_path.exists() and grades_path.exists()),
                    track_record_absent=mode == MODE_GATE and not track_path.exists(),
                    missing=[str(p) for p in missing],
                ),
                flush=True,
            )
        else:
            for path in missing:
                print(
                    f"::notice title=qledger-metric-validity::{mode} mode: input absent, "
                    f"NOT audited: {path}",
                    flush=True,
                )
        return 0

    claims = _read_jsonl(claims_path)
    grades = _read_jsonl(grades_path)

    if mode == MODE_STORE:
        findings = audit(claims, grades)
    else:
        track_record = json.loads(track_path.read_text(encoding="utf-8"))
        fam_map, desk_map = derive_reported_metrics(track_record)
        findings = audit(claims, grades, reported_metrics=fam_map, group_by=GROUP_FAMILY)
        findings += audit(claims, grades, reported_metrics=desk_map, group_by=GROUP_DESK)

    _emit(findings, args.json, len(claims), len(grades), mode=mode)
    invalid = [f for f in findings if f.severity == SEVERITY_INVALID]
    if not args.json:
        suffix = (
            f", published metrics read from {track_path.relative_to(args.root)}"
            if mode == MODE_GATE
            else ", permissive whole-store advisory (never a CI gate)"
        )
        print(
            f"qledger metric validity [{mode}]: {len(claims)} claims, {len(grades)} grades, "
            f"{len(findings)} finding(s) ({len(invalid)} invalid){suffix}",
            flush=True,
        )
    if args.strict and invalid:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
