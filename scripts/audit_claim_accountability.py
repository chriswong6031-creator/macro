"""Standing audit: claim accountability — falsifier coverage, gradeability, and
ontology fill per desk and claim_family.

NW Codex Three Lobes — W-A (PR-B) — RUL-C3/C8/C9.

Reads (read-only, never writes to these):
  data/qledger/claims.jsonl          — QI-owned claim store
  data/qledger/grades.jsonl          — QI-owned grade store
  site/qledger/track_record.json     — nightly grader output

Per desk and per claim_family emits:
  n_claims               : total claim count
  falsifier_coverage     : fraction with a non-null falsifier
  hit_gradeable_share    : fraction with direction != 0
                           NOTE: direction=0 claims are graded on excess only
                           (not hit-gradeable); label printed explicitly so the
                           result cannot be read as contradicting the R2 audit's
                           CLOSED verdict on the qledger.
  maturity_mix           : share graded at horizon_d=5; matured counts at 21d/63d
                           (both 0 today — calendar-gated, not build-gated)
  fill_convention_split  : asof_legacy vs next_bar grade counts (#1180 discontinuity)
  source_ontology_fill   : source_tier / channels / source_id fill rates —
                           honesty row showing why per-source reliability is
                           not yet computable

Writes:
  data/governance/claim_accountability.json   (git-committed, single-writer)
  docs/CLAIM_ACCOUNTABILITY.md                (regenerated from json; never
                                               co-owned with docs/GRADING_CLOSURE.md)

Wired as an end-of-collect audit step — must finish in seconds and NEVER raise.

Usage:
    python -m scripts.audit_claim_accountability           # writes both outputs
    python -m scripts.audit_claim_accountability --check   # prints, no writes
    python -m scripts.audit_claim_accountability --root /path/to/repo
    python -m scripts.audit_claim_accountability --json    # JSON to stdout
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("audit_claim_accountability")

# ---------------------------------------------------------------------------
# I/O HELPERS
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file; return empty list on any failure."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]
    except Exception:
        return []


def _read_json(path: Path) -> dict:
    """Load a JSON file; return empty dict on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# CORE AUDIT LOGIC
# ---------------------------------------------------------------------------

def _safe_div(num: int | float, denom: int | float) -> float | None:
    """Return num/denom rounded to 6dp, or None if denom is zero."""
    if not denom:
        return None
    return round(num / denom, 6)


def _audit_group(claims: list[dict], grades_by_claim: dict[str, list[dict]]) -> dict[str, Any]:
    """Compute accountability metrics for a list of claims.

    Parameters
    ----------
    claims:
        List of claim dicts belonging to one desk or claim_family.
    grades_by_claim:
        Mapping claim_id → list of grade dicts (all horizons, all conventions).

    Returns
    -------
    Dict with all accountability fields.
    """
    n_claims = len(claims)
    if n_claims == 0:
        return {
            "n_claims": 0,
            "falsifier_coverage": None,
            "hit_gradeable_share": None,
            "hit_gradeable_note": (
                "direction=0 claims are not hit-gradeable (graded on excess only)"
            ),
            "maturity_mix": {
                "graded_5d_share": None,
                "matured_21d_count": 0,
                "matured_63d_count": 0,
                "note": "no claims in this group",
            },
            "fill_convention_split": {
                "asof_legacy_count": 0,
                "next_bar_count": 0,
                "note": "#1180 discontinuity — asof_legacy = pre-#1180 grades (fill_convention absent)",
            },
            "source_ontology_fill": {
                "source_tier_fill_rate": None,
                "channels_fill_rate": None,
                "source_id_fill_rate": None,
                "note": (
                    "near-zero fill; per-source reliability not yet computable "
                    "(QI masterplan: >=500 graded labels gate)"
                ),
            },
        }

    # --- falsifier coverage ---
    n_with_falsifier = sum(1 for c in claims if c.get("falsifier") is not None)

    # --- hit-gradeability ---
    # direction=0 claims are graded on excess only, not on hit.
    # This is a structural property of the qledger schema — documenting it
    # does NOT contradict the R2 audit's CLOSED verdict.
    n_hit_gradeable = sum(1 for c in claims if c.get("direction") != 0)

    # --- maturity mix (grades for these claims) ---
    all_grades: list[dict] = []
    for c in claims:
        cid = c.get("claim_id")
        if cid:
            all_grades.extend(grades_by_claim.get(cid, []))

    n_graded_5d = sum(1 for g in all_grades if g.get("horizon_d") == 5)
    n_graded_21d = sum(1 for g in all_grades if g.get("horizon_d") == 21)
    n_graded_63d = sum(1 for g in all_grades if g.get("horizon_d") == 63)

    # --- fill_convention split ---
    # asof_legacy: fill_convention field absent or None (pre-#1180 grader)
    # next_bar: fill_convention == 'next_bar' (#1180+ grader)
    n_asof_legacy = sum(
        1 for g in all_grades if g.get("fill_convention") is None
    )
    n_next_bar = sum(
        1 for g in all_grades if g.get("fill_convention") == "next_bar"
    )

    # --- source ontology fill ---
    n_source_tier = sum(1 for c in claims if c.get("source_tier") is not None)
    n_channels = sum(1 for c in claims if c.get("channels") is not None)
    n_source_id = sum(1 for c in claims if c.get("source_id") is not None)

    return {
        "n_claims": n_claims,
        "falsifier_coverage": _safe_div(n_with_falsifier, n_claims),
        "n_with_falsifier": n_with_falsifier,
        "hit_gradeable_share": _safe_div(n_hit_gradeable, n_claims),
        "n_hit_gradeable": n_hit_gradeable,
        "hit_gradeable_note": (
            "direction=0 claims are not hit-gradeable (graded on excess only); "
            "this does not contradict the R2 audit CLOSED verdict"
        ),
        "maturity_mix": {
            "graded_5d_count": n_graded_5d,
            "graded_5d_share": _safe_div(n_graded_5d, n_claims),
            "matured_21d_count": n_graded_21d,
            "matured_63d_count": n_graded_63d,
            "note": (
                "21d/63d matured counts are 0 today — calendar-gated, not build-gated; "
                "earliest useful read ~2026-10-01"
            ),
        },
        "fill_convention_split": {
            "asof_legacy_count": n_asof_legacy,
            "next_bar_count": n_next_bar,
            "note": (
                "#1180 discontinuity — asof_legacy = pre-#1180 grades "
                "(fill_convention field absent in grade); "
                "next_bar = post-#1180 (fill_convention='next_bar')"
            ),
        },
        "source_ontology_fill": {
            "source_tier_fill_rate": _safe_div(n_source_tier, n_claims),
            "n_source_tier": n_source_tier,
            "channels_fill_rate": _safe_div(n_channels, n_claims),
            "n_channels": n_channels,
            "source_id_fill_rate": _safe_div(n_source_id, n_claims),
            "n_source_id": n_source_id,
            "note": (
                "near-zero fill across most desks; per-source reliability curve "
                "unbuildable from current data (QI masterplan: >=500 graded labels gate)"
            ),
        },
    }


# ---------------------------------------------------------------------------
# MAIN RUN
# ---------------------------------------------------------------------------

def run(root: Path | None = None, write: bool = True) -> dict:
    """Run the full claim-accountability audit.  Returns payload dict."""
    t0 = time.monotonic()
    if root is None:
        root = Path(__file__).resolve().parent.parent

    claims_path = root / "data" / "qledger" / "claims.jsonl"
    grades_path = root / "data" / "qledger" / "grades.jsonl"
    track_record_path = root / "site" / "qledger" / "track_record.json"

    claims = _read_jsonl(claims_path)
    grades = _read_jsonl(grades_path)
    track_record = _read_json(track_record_path)

    # Build grade lookup: claim_id -> list of grade dicts
    grades_by_claim: dict[str, list[dict]] = defaultdict(list)
    for g in grades:
        cid = g.get("claim_id")
        if cid:
            grades_by_claim[cid].append(g)

    # --- global summary ---
    n_claims_global = len(claims)
    n_grades_global = len(grades)
    n_falsifier_global = sum(1 for c in claims if c.get("falsifier") is not None)

    # --- per-desk ---
    desk_buckets: dict[str, list[dict]] = defaultdict(list)
    for c in claims:
        desk_buckets[c.get("desk") or "unknown"].append(c)

    by_desk: dict[str, dict] = {}
    for desk in sorted(desk_buckets):
        by_desk[desk] = _audit_group(desk_buckets[desk], grades_by_claim)

    # empty desks appear with zeros, not dropped — include all desks seen in claims

    # --- per-family ---
    family_buckets: dict[str, list[dict]] = defaultdict(list)
    for c in claims:
        family_buckets[c.get("claim_family") or "unknown"].append(c)

    by_family: dict[str, dict] = {}
    for family in sorted(family_buckets):
        by_family[family] = _audit_group(family_buckets[family], grades_by_claim)

    # --- track_record summary (read-only reference) ---
    tr_summary: dict[str, Any] = {}
    if track_record:
        tr_summary = {
            "generated_at": track_record.get("generated_at"),
            "grade_horizons": track_record.get("grade_horizons"),
            "desks_in_track_record": sorted(track_record.get("by_desk", {}).keys()),
            "note": (
                "track_record.json is the scoring core (hit_rate, wilson_ci_low, "
                "excess_mean, ACCRUING/UNGRADED states); this audit is the "
                "coverage/accountability complement — not a duplicate"
            ),
        }

    payload: dict[str, Any] = {
        "schema": "claim_accountability.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "global": {
            "n_claims": n_claims_global,
            "n_grades": n_grades_global,
            "n_with_falsifier": n_falsifier_global,
            "falsifier_coverage": _safe_div(n_falsifier_global, n_claims_global),
            "falsifier_coverage_note": (
                "~146/9069 = 1.6% global as of 2026-07-06; "
                "falsifier-starvation is a structural property of importance-signal "
                "and china_news desks, not a grader failure"
            ),
        },
        "by_desk": by_desk,
        "by_family": by_family,
        "track_record_ref": tr_summary,
    }

    elapsed = time.monotonic() - t0
    log.info(
        "claim_accountability audit: %d claims / %d grades — "
        "falsifier_coverage=%.1f%% (%.2fs)",
        n_claims_global, n_grades_global,
        100 * (n_falsifier_global / n_claims_global) if n_claims_global else 0,
        elapsed,
    )

    if write:
        _write_json(payload, root)
        _write_md(payload, root)

    return payload


# ---------------------------------------------------------------------------
# WRITERS
# ---------------------------------------------------------------------------

def _write_json(payload: dict, root: Path) -> None:
    """Write data/governance/claim_accountability.json."""
    out = root / "data" / "governance" / "claim_accountability.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, separators=(",", ": ")))
        log.info("claim_accountability: wrote %s", out)
    except Exception as exc:  # noqa: BLE001
        log.warning("claim_accountability: json write failed: %s", exc)


def _write_md(payload: dict, root: Path) -> None:
    """Write / overwrite docs/CLAIM_ACCOUNTABILITY.md (regenerated from JSON)."""
    g = payload["global"]
    by_desk = payload["by_desk"]
    by_family = payload["by_family"]

    lines: list[str] = []
    lines.append("# Claim Accountability — QI Ledger Coverage Audit")
    lines.append("")
    lines.append(
        f"Generated: {payload['generated_at']}  "
        f"— {g['n_claims']} claims / {g['n_grades']} grades  "
        f"— falsifier coverage: {g['n_with_falsifier']}/{g['n_claims']} "
        f"({100 * (g['falsifier_coverage'] or 0):.1f}%)"
    )
    lines.append("")
    lines.append(
        "**Read-only over `data/qledger/` (QI-owned, RUL-C3).** "
        "This audit makes coverage/accountability standing and visible — "
        "it is the complement of `track_record.json` (scoring core), not a replacement."
    )
    lines.append("")
    lines.append(
        "**Hit-gradeable note:** `direction=0` claims are graded on excess only "
        "(not hit-gradeable). This structural property does NOT contradict the "
        "R2 audit CLOSED verdict on the qledger."
    )
    lines.append("")
    lines.append(
        "**Maturity note:** 21d/63d matured counts are 0 today — calendar-gated, "
        "not build-gated. Earliest useful read ~2026-10-01."
    )
    lines.append("")
    lines.append(
        "**Source ontology note:** per-source reliability curve is unbuildable from "
        "current data (near-zero fill). QI masterplan gate: >=500 graded labels."
    )
    lines.append("")

    # --- global table ---
    lines.append("## Global summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| n_claims | {g['n_claims']} |")
    lines.append(f"| n_grades | {g['n_grades']} |")
    lines.append(f"| n_with_falsifier | {g['n_with_falsifier']} |")
    fc = g["falsifier_coverage"]
    lines.append(f"| falsifier_coverage | {fc:.4f} ({100*fc:.1f}%) |" if fc is not None else "| falsifier_coverage | — |")
    lines.append("")

    # --- per-desk table ---
    lines.append("## Per-desk breakdown")
    lines.append("")
    lines.append(
        "| Desk | n_claims | falsifier_cov | hit_gradeable | "
        "graded_5d | matured_21d | matured_63d | "
        "asof_legacy | next_bar | "
        "src_tier_fill | channels_fill | src_id_fill |"
    )
    lines.append(
        "|------|----------|--------------|--------------|"
        "----------|-------------|-------------|"
        "------------|----------|"
        "-------------|--------------|------------|"
    )
    for desk, row in sorted(by_desk.items()):
        fc_val = row["falsifier_coverage"]
        hg_val = row["hit_gradeable_share"]
        mm = row["maturity_mix"]
        fcs = row["fill_convention_split"]
        sof = row["source_ontology_fill"]
        lines.append(
            f"| `{desk}` "
            f"| {row['n_claims']} "
            f"| {_pct(fc_val)} "
            f"| {_pct(hg_val)} "
            f"| {mm['graded_5d_count']} "
            f"| {mm['matured_21d_count']} "
            f"| {mm['matured_63d_count']} "
            f"| {fcs['asof_legacy_count']} "
            f"| {fcs['next_bar_count']} "
            f"| {_pct(sof['source_tier_fill_rate'])} "
            f"| {_pct(sof['channels_fill_rate'])} "
            f"| {_pct(sof['source_id_fill_rate'])} |"
        )
    lines.append("")

    # --- per-family table ---
    lines.append("## Per-family breakdown")
    lines.append("")
    lines.append(
        "| Family | n_claims | falsifier_cov | hit_gradeable | "
        "graded_5d | matured_21d | matured_63d |"
    )
    lines.append(
        "|--------|----------|--------------|--------------|"
        "----------|-------------|-------------|"
    )
    for fam, row in sorted(by_family.items()):
        fc_val = row["falsifier_coverage"]
        hg_val = row["hit_gradeable_share"]
        mm = row["maturity_mix"]
        lines.append(
            f"| `{fam}` "
            f"| {row['n_claims']} "
            f"| {_pct(fc_val)} "
            f"| {_pct(hg_val)} "
            f"| {mm['graded_5d_count']} "
            f"| {mm['matured_21d_count']} "
            f"| {mm['matured_63d_count']} |"
        )
    lines.append("")

    lines.append("> Source of truth: `data/governance/claim_accountability.json`")
    lines.append("> Generated by `scripts/audit_claim_accountability.py` (end-of-collect step).")
    lines.append("")

    out = root / "docs" / "CLAIM_ACCOUNTABILITY.md"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines))
        log.info("claim_accountability: wrote %s", out)
    except Exception as exc:  # noqa: BLE001
        log.warning("claim_accountability: md write failed: %s", exc)


def _pct(val: float | None) -> str:
    """Format a fraction as a percentage string for markdown tables."""
    if val is None:
        return "—"
    return f"{100 * val:.1f}%"


# ---------------------------------------------------------------------------
# COLLECT STEP HOOK
# ---------------------------------------------------------------------------

def run_as_collect_step() -> None:
    """End-of-collect hook — must never raise; wraps run() in a broad except."""
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        log.error("[claim_accountability] audit crashed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="print results without writing outputs")
    ap.add_argument("--root", default=None,
                    help="repo root (default: parent of scripts/)")
    ap.add_argument("--json", action="store_true",
                    help="print JSON summary to stdout")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    root = Path(args.root) if args.root else None
    payload = run(root=root, write=not args.check)

    if args.json or args.check:
        print(json.dumps(payload, indent=2))
    else:
        g = payload["global"]
        fc = g["falsifier_coverage"] or 0
        print(f"\nClaim Accountability Audit — {payload['generated_at'][:10]}")
        print(f"  {g['n_claims']} claims / {g['n_grades']} grades")
        print(f"  falsifier_coverage: {g['n_with_falsifier']}/{g['n_claims']} = {100*fc:.1f}%\n")
        hdr = "{:<32} {:>8} {:>14} {:>14}"
        print(hdr.format("Desk", "n_claims", "falsifier_cov", "hit_gradeable"))
        print("-" * 74)
        for desk, row in sorted(payload["by_desk"].items()):
            print(hdr.format(
                desk[:32],
                row["n_claims"],
                _pct(row["falsifier_coverage"]),
                _pct(row["hit_gradeable_share"]),
            ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
