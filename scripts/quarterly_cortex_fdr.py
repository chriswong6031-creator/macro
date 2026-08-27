"""scripts/quarterly_cortex_fdr.py — Quarterly BH-FDR batch over the cortex family.

The consumer that scripts/evaluate_cortex_hypotheses.py has promised since W7b
PR2 and that never existed.  Its absence was W1 of the 2026-08-26 experiments
audit (research/EXPERIMENTS_AUDIT_2026_08_26.md §3): the evaluator's docstring,
its governance events and config/dag.yml all told hypotheses they were "queued
for the quarterly cortex FDR batch", zero batches ever ran, and the one standing
'passed' verdict (H5) sat in the experiments panel as a ready flag with no
consumer to read it.

WHAT THIS IS FOR
----------------
A cortex 'passed' verdict is ONE gate clearing on ONE hypothesis.  The cortex
files hypotheses continuously against a shared family, so without a
multiple-testing account the family's best-looking member is guaranteed to look
good eventually.  This batch is that account: Benjamini-Hochberg over the
quarter's eligible p-values at a pre-declared q.

WHAT THIS IS NOT
----------------
It does not promote anything.  Surviving BH is a necessary condition for leaving
shadow, never a sufficient one, and no authority, rank, size or gate anywhere in
the system reads this artifact.  The batch RECORDS a statistical verdict; a
promotion remains a separate, human-gated act.  Per house epistemics law the
gauntlet is the PROMOTION gate — display-tier accrual never waits on it.

THE ELIGIBILITY FENCE (why a batch can legitimately promote nobody)
--------------------------------------------------------------------
Running BH over whatever happens to say 'passed' would launder instrument
artifacts into promotions, which is precisely how the audit found the panel.
A verdict reaches the BH pool only if ALL of:

  1. evaluator_version >= MIN_EVALUATOR_VERSION.  Verdicts minted by W7b-PR2 or
     earlier were produced by an instrument with five known wiring defects
     (no feature conditions, no contrast group, mis-spaced gates, a dead Path B,
     status-only writes).  They are not evidence about their hypotheses.
  2. A p_value exists.  A gate clearing a threshold is not a significance test;
     only the contrast metrics carry one.
  3. gate_informative is True.  A gate whose threshold sits on the permissive
     side of its own base rate restates the base rate (H5's hit_rate >= 0.05
     against a measured 0.4533; H4's stop_out_rate >= 0.05 against 0.8246).
     Null is NOT treated as True — an unmeasurable gate is fenced, not assumed.
  4. episode_n >= MIN_EPISODES.  Horizons overlap, so rows are not independent
     draws; 5,524 rows from 3 fire dates is 3 episodes.  BH over row-count
     p-values would be arithmetic on a sample size that does not exist.

Every ineligible verdict is listed in the artifact with its reason.  A batch that
promotes nobody because nothing is eligible is a correct batch, and the artifact
says which fence each candidate hit.

Usage:
    python -m scripts.quarterly_cortex_fdr                 # current quarter
    python -m scripts.quarterly_cortex_fdr --quarter 2026Q3
    python -m scripts.quarterly_cortex_fdr --dry-run       # compute only
    python -m scripts.quarterly_cortex_fdr --q 0.05        # override the FDR level
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

_BATCH_VERSION = "cortex-fdr-v1"

#: Pre-declared false-discovery rate.  Fixed here, never read from a hypothesis —
#: a family that could choose its own q has no multiple-testing account at all.
DEFAULT_Q = 0.10

#: Verdicts from an evaluator older than this carry the audit's five wiring
#: defects and are excluded by name.  Ordering is lexicographic on the version
#: string, which is why the scheme is zero-padded-compatible (W7b-PR2 < W7b-PR3).
MIN_EVALUATOR_VERSION = "W7b-PR3"

#: Distinct as_of dates required before a p-value is treated as a sample.
MIN_EPISODES = 8

FDR_FAMILY = "cortex"


# ---------------------------------------------------------------------------
# Benjamini-Hochberg
# ---------------------------------------------------------------------------

def benjamini_hochberg(pvalues: list[float], q: float) -> list[bool]:
    """Return the BH reject/accept mask for `pvalues` at level `q`.

    Standard step-up procedure: sort ascending, find the largest k with
    p_(k) <= k/m * q, reject every hypothesis at or below that rank.  Returns a
    mask in the ORIGINAL input order.
    """
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    k_max = 0
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= (rank / m) * q:
            k_max = rank
    mask = [False] * m
    for rank, idx in enumerate(order, start=1):
        if rank <= k_max:
            mask[idx] = True
    return mask


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

def _quarter_of(d: date) -> str:
    return f"{d.year}Q{((d.month - 1) // 3) + 1}"


def _quarter_bounds(quarter: str) -> tuple[date, date]:
    year = int(quarter[:4])
    qn = int(quarter[-1])
    start_month = 3 * (qn - 1) + 1
    start = date(year, start_month, 1)
    end = date(year + 1, 1, 1) if qn == 4 else date(year, start_month + 3, 1)
    return start, end


def assess_eligibility(row: dict) -> tuple[bool, str | None, dict[str, Any]]:
    """Decide whether one 'passed' row may enter the BH pool.

    Returns (eligible, reason_if_not, facts).  Fail-closed: anything missing or
    unparseable is ineligible, never assumed adequate.
    """
    detail = row.get("evaluation_detail") or {}
    facts = {
        "evaluator_version": detail.get("evaluator_version"),
        "p_value": detail.get("p_value"),
        "gate_informative": detail.get("gate_informative"),
        "episode_n": detail.get("episode_n"),
        "metric": detail.get("metric") or (row.get("pre_committed_gate") or {}).get("metric"),
        "metric_value": row.get("metric_value"),
        "n": row.get("evaluation_n"),
    }

    version = facts["evaluator_version"]
    if not version:
        return False, "no evaluator_version recorded (pre-repair verdict)", facts
    if str(version) < MIN_EVALUATOR_VERSION:
        return False, (
            f"evaluator {version} predates {MIN_EVALUATOR_VERSION}; the verdict "
            f"is an instrument artifact (audit §3 W1-W6)"
        ), facts

    p = facts["p_value"]
    if p is None:
        return False, (
            "no p_value — the gate cleared a threshold but no significance test "
            "was computed (absolute-metric gates carry none)"
        ), facts
    try:
        p = float(p)
    except (TypeError, ValueError):
        return False, f"p_value {p!r} is not numeric", facts
    if not (0.0 <= p <= 1.0):
        return False, f"p_value {p} outside [0, 1]", facts

    if facts["gate_informative"] is not True:
        return False, (
            "gate_informative is not True — the threshold does not discriminate "
            "against its own base rate, so clearing it is not evidence"
        ), facts

    episodes = facts["episode_n"]
    try:
        episodes = int(episodes)
    except (TypeError, ValueError):
        return False, "no episode_n recorded — independent sample size unknown", facts
    if episodes < MIN_EPISODES:
        return False, (
            f"episode_n {episodes} < {MIN_EPISODES}; overlapping horizons mean "
            f"row count is not sample size"
        ), facts

    facts["p_value"] = p
    facts["episode_n"] = episodes
    return True, None, facts


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def run_batch(
    root: Path | str | None = None,
    quarter: str | None = None,
    q: float = DEFAULT_Q,
    dry_run: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    """Run one quarterly FDR batch.  Returns the batch artifact dict."""
    root = Path(root) if root is not None else _ROOT
    if today is None:
        today = datetime.now(timezone.utc).date()
    quarter = quarter or _quarter_of(today)
    q_start, q_end = _quarter_bounds(quarter)

    from engine.neuralweb.metabolism import _cortex_rows_latest  # type: ignore[import]

    rows = _cortex_rows_latest(str(root))

    candidates: list[dict] = []
    for row in rows:
        if row.get("status") != "passed":
            continue
        if str(row.get("fdr_family") or FDR_FAMILY) != FDR_FAMILY:
            continue
        stamped = str(row.get("evaluated_at") or "")[:10]
        if stamped:
            try:
                d = date.fromisoformat(stamped)
            except ValueError:
                d = None
            if d is not None and not (q_start <= d < q_end):
                continue
        candidates.append(row)

    eligible: list[dict] = []
    ineligible: list[dict] = []
    for row in candidates:
        ok, reason, facts = assess_eligibility(row)
        entry = {
            "id": row.get("id"),
            "hypothesis": str(row.get("hypothesis") or "")[:160],
            "claim_shape": row.get("claim_shape"),
            "evaluated_at": row.get("evaluated_at"),
            **facts,
        }
        if ok:
            eligible.append(entry)
        else:
            entry["ineligible_reason"] = reason
            ineligible.append(entry)

    pvals = [float(e["p_value"]) for e in eligible]
    mask = benjamini_hochberg(pvals, q)
    for entry, survived in zip(eligible, mask):
        entry["bh_survivor"] = bool(survived)

    survivors = [e["id"] for e in eligible if e["bh_survivor"]]

    artifact: dict[str, Any] = {
        "schema": "neuralweb.cortex_fdr_batch.v1",
        "batch_version": _BATCH_VERSION,
        "quarter": quarter,
        "family": FDR_FAMILY,
        "q": q,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "min_evaluator_version": MIN_EVALUATOR_VERSION,
        "min_episodes": MIN_EPISODES,
        "n_candidates": len(candidates),
        "n_eligible": len(eligible),
        "n_ineligible": len(ineligible),
        "n_survivors": len(survivors),
        "survivors": survivors,
        "eligible": eligible,
        "ineligible": ineligible,
        "promotion_note": (
            "Surviving BH is NECESSARY, never sufficient, to leave shadow.  This "
            "artifact changes no authority, rank, size or gate; promotion is a "
            "separate human-gated act."
        ),
    }

    if len(candidates) and not len(eligible):
        # Loud, not silent: a batch that promotes nobody because everything was
        # fenced must say so in the Actions summary, or "0 survivors" reads as
        # "nothing qualified on the merits".
        print(
            f"::warning title=cortex-fdr-all-fenced::"
            f"{quarter}: {len(candidates)} passed verdict(s), 0 eligible for BH "
            f"— every candidate hit the eligibility fence; see artifact",
            flush=True,
        )

    if not dry_run:
        out_dir = root / "data" / "neuralweb" / "cortex" / "fdr_batches"
        batch_path = out_dir / f"{quarter}.json"

        # The batch is quarter-scoped but runs on the nightly cadence, so it
        # recomputes the same quarter many times.  A governance event is only
        # meaningful when the DECISION changed — append one per re-run and the
        # ledger fills with identical rows and stops being readable.
        decision = {
            "survivors": sorted(survivors),
            "eligible": sorted(e["id"] for e in eligible),
            "ineligible": sorted(e["id"] for e in ineligible),
            "q": q,
        }
        prior_decision = None
        if batch_path.exists():
            try:
                prior = json.loads(batch_path.read_text(encoding="utf-8"))
                prior_decision = {
                    "survivors": sorted(prior.get("survivors") or []),
                    "eligible": sorted(e["id"] for e in (prior.get("eligible") or [])),
                    "ineligible": sorted(e["id"] for e in (prior.get("ineligible") or [])),
                    "q": prior.get("q"),
                }
            except Exception:  # noqa: BLE001
                prior_decision = None
        decision_changed = decision != prior_decision
        artifact["decision_changed"] = decision_changed

        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            batch_path.write_text(
                json.dumps(artifact, indent=2, default=str), encoding="utf-8"
            )
            (out_dir.parent / "fdr_latest.json").write_text(
                json.dumps(artifact, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("cortex-fdr: could not write batch artifact (%s)", exc)

        if not decision_changed:
            log.info(
                "cortex-fdr: %s decision unchanged — artifact refreshed, no "
                "governance event appended", quarter,
            )
            return artifact

        try:
            from engine.neuralweb.governance import append_event  # type: ignore[import]
            append_event(
                "article3_review",
                target=f"cortex_fdr_batch:{quarter}",
                article=3,
                authored_by="quarterly_cortex_fdr",
                evidence={
                    "quarter": quarter,
                    "q": q,
                    "n_candidates": len(candidates),
                    "n_eligible": len(eligible),
                    "n_survivors": len(survivors),
                    "survivors": survivors,
                    "ineligible_reasons": [
                        {"id": e["id"], "reason": e["ineligible_reason"]}
                        for e in ineligible
                    ],
                },
                note=(
                    f"quarterly BH-FDR over family={FDR_FAMILY} at q={q}: "
                    f"{len(survivors)}/{len(eligible)} eligible survived "
                    f"({len(ineligible)} fenced). Survival is necessary, not "
                    f"sufficient, for promotion beyond shadow."
                ),
                root=str(root),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("cortex-fdr: governance event failed (%s)", exc)

    return artifact


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [cortex_fdr] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Quarterly BH-FDR batch over the cortex hypothesis family"
    )
    parser.add_argument("--root", default=None, help="Repo root override")
    parser.add_argument("--quarter", default=None, help="e.g. 2026Q3 (default: current)")
    parser.add_argument("--q", type=float, default=DEFAULT_Q, help="FDR level")
    parser.add_argument("--dry-run", action="store_true", help="Compute only; no writes")
    args = parser.parse_args(argv)

    try:
        artifact = run_batch(
            root=args.root, quarter=args.quarter, q=args.q, dry_run=args.dry_run
        )
        print(json.dumps(artifact, indent=2, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("cortex-fdr: fatal error (%s)", exc, exc_info=True)
        # Degrade-never-raise, matching the evaluator's nightly contract.
        return 0


if __name__ == "__main__":
    sys.exit(main())
