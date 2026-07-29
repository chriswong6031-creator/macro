"""scripts/run_research_triage.py — W2R nightly research triage (XG-W8).

Ranks EVERY institutional report in the vault window with the deterministic
W-score, runs the demote-only LLM veto pass over the ranked head, and appends
one score row per report to data/press/research_triage.jsonl.

    python -m scripts.run_research_triage                # dry run, NO spend
    python -m scripts.run_research_triage --veto         # dry run WITH the veto pass
    python -m scripts.run_research_triage --write        # append the ledger + veto
    python -m scripts.run_research_triage --write --no-veto
    python -m scripts.run_research_triage --write --compact   # + ledger retention
    python -m scripts.run_research_triage --as-of 2026-07-28 --top 20

THE DEFAULT IS THE SAFE ONE, AND THAT NOW INCLUDES THE MONEY.  A bare run
computes and prints the whole ranking and writes NOTHING — no ledger row, and
**no LLM call**.  The first version ran the veto pass on a dry run while this
docstring claimed it did not: the flag governed the ledger and nothing else, so
every `--dry-run` cost real tokens.  Spend on a dry run is now an explicit
`--veto` opt-in.  `--write` keeps the veto ON by default (that is the nightly's
whole job) and `--no-veto` turns it off there.

WHY THIS IS A SEPARATE LANE FROM press-publish.yml, stated because the
alternative looks tempting:

  * The masterplan requires triage to rank ALL inflow DAILY "regardless of armed
    slots".  Folding it into the press lane would have gated the day's scores on
    PRESS_PUBLISH_ENABLED — the ledger would go dark exactly while the operator
    was deciding whether to arm publishing, which is when it is most useful.
  * scripts/run_press.py --staging has a TESTED invariant that it writes nothing
    outside data/press/staging/ (tests/test_press_run.py). The score ledger is a
    tracked repo file, so it cannot be written from there without breaking the
    invariant that keeps a staging run harmless.
  * The press lane runs weekdays; research arrives seven days a week.

REPO-WRITE POSTURE.  This is a NIGHTLY-CLASS lane (a scheduled GitHub Actions
job with `contents: write`), not a VPS daemon, so a tracked ledger append is
legal here — the same posture research-ingest.yml uses to commit the vault
catalog snapshot, and the opposite of the press daemon's zero-repo-write rule.
It appends to ONE file and the workflow git-adds that one path.

SPEND.  The veto pass is the only network call, it goes through the existing
engine.llm_auth waterfall, and its usage lands in the existing lib.ai_costs
ledger under `press-research-triage-veto`.  No credential visible means no veto
and an unmodified deterministic ranking — the safe direction, because the veto
can only ever have lowered a rank.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.press import (  # noqa: E402
    desk_planner, research_lane, research_triage, research_veto,
)

log = logging.getLogger("run_research_triage")


def _annotate(level: str, title: str, message: str) -> None:
    """Bare print, line start, flushed — a logger prefix makes GitHub drop it."""
    print(f"::{level} title={title}::{message}", flush=True)


def load_marketing_cfg(root: Path) -> dict:
    """config/marketing.yml — the liveness + outbox contract for the X lane."""
    import yaml  # noqa: PLC0415

    path = root / "config" / "marketing.yml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("research triage: marketing config unreadable (%s)", exc)
        return {}


def build_research_x_shapes(root: Path, result: dict, catalog: dict[str, dict],
                            *, as_of: str, enqueue: bool) -> dict:
    """Compose the Mastermind Research X shapes for today's selected reports.

    THIS IS THE LANE'S PRODUCTION CALL SITE.  `engine/press/research_lane.py`
    had none in its first version — every one of its behaviours was exercised
    only by tests, which is the vacuous-green shape the program's own law names.
    A dark feature still has to be REACHED by production code; the dark state is
    then a no-op that says so, and arming it is a config flip rather than a
    build.

    Liveness is the SAME machinery mastermind_news uses (engine.marketing.
    accounts, reading desk_network + the override file), so this returns
    `state="dark"` with an empty item list until the operator creates the
    account.  Nothing here can post: `enqueue` only ever reaches a queue whose
    account has no Buffer channel.
    """
    marketing_cfg = load_marketing_cfg(root)
    selected = [r for r in (result.get("rows") or []) if r.get("status") == "selected"]
    pieces = [
        {"report": catalog[str(r.get("report_id"))], "triage": r}
        for r in selected if str(r.get("report_id")) in catalog
    ]
    report = research_lane.build_items(
        pieces, cfg=marketing_cfg, root=root, as_of=as_of,
        enqueue=enqueue, catalog_items=list(catalog.values()))
    if report.get("state") == "dark":
        # NOT a warning: this is the designed state until X Growth §7 lever 1.
        log.info("research triage: X lane dark (%s) — %d selected report(s) "
                 "composed nothing", report.get("reason"), len(pieces))
    return report


def load_catalog(root: Path) -> list[dict]:
    """The committed vault catalog snapshot ([] when absent or malformed)."""
    path = root / "data" / "research_vault" / "catalog.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("research triage: catalog unreadable (%s)", exc)
        return []
    items = (payload or {}).get("items")
    return [it for it in items if isinstance(it, dict)] if isinstance(items, list) else []


def run(root: Path, *, as_of: str | None = None, write: bool = False,
        veto: bool = True, top: int = 10, compact: bool = False) -> dict:
    cfg = desk_planner.load_config(root)
    if not cfg:
        _annotate("error", "research_triage_config",
                  "config/press.yml is missing or unparsable — triage cannot run")
        return {"ok": False, "reason": "no_config"}
    # Read AFTER the guard: on an unparsable config this used to run first and
    # dig a block out of {} before the error path fired.
    tcfg = research_triage.triage_config(cfg)
    if not bool(tcfg.get("enabled", True)):
        _annotate("notice", "research_triage",
                  "research_triage.enabled is false — nothing ranked, nothing written")
        return {"ok": True, "state": "disabled", "rows": 0}

    items = load_catalog(root)
    if not items:
        _annotate("warning", "research_triage_empty",
                  "research vault catalog is empty or unreadable — no reports triaged "
                  "today. That is a vault-ingest problem, not a thin news day.")
        return {"ok": True, "state": "no_catalog", "rows": 0}

    run_date = as_of or date.today().isoformat()
    result = research_triage.rank(items, as_of=run_date, root=root, cfg=cfg)

    veto_report = {"state": "skipped", "vetoes": {}, "batches": 0, "head": 0}
    if veto:
        catalog = {str(it.get("id") or ""): it for it in items}
        veto_report = research_veto.run(result, cfg=tcfg, catalog=catalog)
        if veto_report.get("vetoes"):
            result = research_triage.apply_vetoes(result, veto_report["vetoes"], cfg=tcfg)

    # The X surface for today's picks. Dark until the operator creates the
    # account; the call site is what makes that darkness a state rather than an
    # absence.
    x_lane = build_research_x_shapes(
        root, result, {str(it.get("id") or ""): it for it in items},
        as_of=run_date, enqueue=write)

    rows = research_triage.ledger_rows(result, cfg=cfg)
    header = research_triage.run_header(result, cfg=cfg, veto_report=veto_report)
    written = 0
    compaction: dict = {}
    if write:
        path = research_triage.ledger_path(cfg, root)
        written = research_triage.append_ledger(path, rows, header=header)
        if compact:
            lcfg = tcfg.get("ledger") if isinstance(tcfg.get("ledger"), dict) else {}
            compaction = research_triage.compact_ledger(
                path,
                retention_days=int(
                    lcfg.get("retention_days")
                    or research_triage._LEDGER_DEFAULTS["retention_days"]),
                as_of=run_date)

    selected = [r for r in result["rows"] if r.get("status") == "selected"]
    dropped = [r for r in result["rows"] if r.get("status") == "garbage_dropped"]
    vol = result["volume"]

    _annotate("notice", "research_triage",
              f"W2R triage {run_date}: ranked {len(result['rows'])} report(s); "
              f"{len(selected)} selected ({vol['stage']}: "
              f"{vol['flagship_per_day']} flagship + {vol['desk_notes_per_day']} notes/day); "
              f"{len(dropped)} garbage-dropped; veto={veto_report.get('state')} "
              f"({len(veto_report.get('vetoes') or {})} demoted); "
              f"ledger rows written={written}")
    if not result.get("near_dup_enabled"):
        _annotate("notice", "research_triage_degraded",
                  "cluster_density ran WITHOUT the near-dup pass (datasketch absent) — "
                  "every density number this run is a FLOOR, and every row says so.")

    effective = result.get("effective_contributions") or {}
    dominant = effective.get("dominant") or {}
    if dominant.get("component"):
        # WHAT THE BLEND ACTUALLY ORDERED ON (review M2). Printing the declared
        # weights alone lets a reader believe a six-component ranking is running
        # when three of the six are constant across the corpus and one term is
        # doing effectively all the ordering.
        _annotate("notice", "research_triage_effective",
                  "W-score effective ordering: dominated by "
                  f"{dominant['component']} (r={dominant.get('corr_with_score')}); "
                  f"inert this run: {', '.join(effective.get('inert') or []) or 'none'}. "
                  "Declared weights state an intent; this states the run.")
    if not result.get("reconciled", True):
        _annotate("warning", "research_triage_reconcile_summary",
                  f"inputs={result.get('inputs')} rows={len(result.get('rows') or [])} "
                  "— one row per input is the ledger's law and this run broke it.")

    summary = {
        "ok": True,
        "state": "ok",
        "as_of": result["as_of"],
        "scoring_version": result["scoring_version"],
        "ranked": len(result["rows"]),
        "selected": len(selected),
        "garbage_dropped": len(dropped),
        "volume": vol,
        "context_states": result["context_states"],
        "near_dup_enabled": result["near_dup_enabled"],
        "veto": {k: v for k, v in veto_report.items() if k != "vetoes"},
        "vetoed": sorted(veto_report.get("vetoes") or {}),
        "inputs": result.get("inputs"),
        "reconciled": result.get("reconciled"),
        "cluster_truncated": result.get("cluster_truncated"),
        "effective_contributions": effective,
        "ledger_rows": len(rows),
        "ledger_written": written,
        "compaction": compaction,
        "x_lane": {"state": x_lane.get("state"), "reason": x_lane.get("reason"),
                   "items": len(x_lane.get("items") or []),
                   "enqueued": x_lane.get("enqueued"),
                   "skipped": len(x_lane.get("skipped") or [])},
        "head": [
            {"rank": r.get("rank"), "tier": r.get("tier"), "w_score": r.get("w_score"),
             "institution": r.get("institution"), "title": r.get("title")[:90],
             "components": r.get("components"), "veto": r.get("veto")}
            for r in result["rows"][:max(0, top)]
        ],
    }
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="W2R research triage (XG-W8).")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="rank and print, write nothing, SPEND NOTHING (default)")
    mode.add_argument("--write", action="store_true",
                      help="append the score rows to the triage ledger (veto ON)")
    veto_group = ap.add_mutually_exclusive_group()
    veto_group.add_argument("--veto", action="store_true",
                            help="run the LLM veto pass. Implied by --write; on a "
                                 "dry run it is the ONLY way to spend a token.")
    veto_group.add_argument("--no-veto", action="store_true",
                            help="skip the LLM veto pass (deterministic ranking only)")
    ap.add_argument("--compact", action="store_true",
                    help="apply ledger.retention_days after writing (--write only)")
    ap.add_argument("--as-of", default="", help="run date YYYY-MM-DD (default: today)")
    ap.add_argument("--root", default="", help="repo root override (tests)")
    ap.add_argument("--top", type=int, default=10,
                    help="how many ranked rows to print in the summary")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    root = Path(args.root).resolve() if args.root else _REPO
    # SPEND IS OPT-IN ON A DRY RUN (review M5). `--write` is the nightly and
    # keeps the veto on; a bare invocation is free unless the caller says --veto.
    if args.no_veto:
        want_veto = False
    elif args.veto:
        want_veto = True
    else:
        want_veto = bool(args.write)
    out = run(root, as_of=(args.as_of or None), write=bool(args.write),
              veto=want_veto, top=args.top, compact=bool(args.compact))
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
