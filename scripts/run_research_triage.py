"""scripts/run_research_triage.py — W2R nightly research triage (XG-W8).

Ranks EVERY institutional report in the vault window with the deterministic
W-score, runs the demote-only LLM veto pass over the ranked head, and appends
one score row per report to data/press/research_triage.jsonl.

    python -m scripts.run_research_triage                # --dry-run (default)
    python -m scripts.run_research_triage --write        # append the ledger
    python -m scripts.run_research_triage --write --no-veto
    python -m scripts.run_research_triage --as-of 2026-07-28 --top 20

THE DEFAULT IS THE SAFE ONE.  `--dry-run` computes and prints the whole ranking
and writes NOTHING — no ledger row, no LLM call, no spend.  `--write` is the
only mode that appends, and `.github/workflows/research-triage.yml` is the only
thing that runs it that way.

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

from engine.press import desk_planner, research_triage, research_veto  # noqa: E402

log = logging.getLogger("run_research_triage")


def _annotate(level: str, title: str, message: str) -> None:
    """Bare print, line start, flushed — a logger prefix makes GitHub drop it."""
    print(f"::{level} title={title}::{message}", flush=True)


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
        veto: bool = True, top: int = 10) -> dict:
    cfg = desk_planner.load_config(root)
    tcfg = research_triage.triage_config(cfg)
    if not cfg:
        _annotate("error", "research_triage_config",
                  "config/press.yml is missing or unparsable — triage cannot run")
        return {"ok": False, "reason": "no_config"}
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

    rows = research_triage.ledger_rows(result, cfg=cfg)
    written = 0
    if write:
        path = research_triage.ledger_path(cfg, root)
        written = research_triage.append_ledger(path, rows)

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
        "ledger_rows": len(rows),
        "ledger_written": written,
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
                      help="rank and print, write nothing (default)")
    mode.add_argument("--write", action="store_true",
                      help="append the score rows to the triage ledger")
    ap.add_argument("--no-veto", action="store_true",
                    help="skip the LLM veto pass (deterministic ranking only)")
    ap.add_argument("--as-of", default="", help="run date YYYY-MM-DD (default: today)")
    ap.add_argument("--root", default="", help="repo root override (tests)")
    ap.add_argument("--top", type=int, default=10,
                    help="how many ranked rows to print in the summary")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    root = Path(args.root).resolve() if args.root else _REPO
    out = run(root, as_of=(args.as_of or None), write=bool(args.write),
              veto=not args.no_veto, top=args.top)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
