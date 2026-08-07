"""Prophet shadow doors — nightly emitter entry point.

Evaluates Door T (theme-relay), Door R (re-arm) and Door W (washout-turn) on the committed
caches and accrues the night's flags to `data/prophet_doors/flags.jsonl`. All construction
lives in `engine/prophet_doors.py`; this is the DAG hook.

NIGHTLY-ONLY: the forward advance happens under `--nightly` (mirroring
scripts/grade_bottom_calls.py and scripts/grade_us_board.py) AND is independently gated by
`engine.ledger_lane.nightly_advance_enabled` (COLLECT_LANE=nightly). Either guard alone stops
a re-render or an intraday lane from appending; both are present because the brief for this
lane is that the ledger is the experiment.

ZERO AUTHORITY: writes only data/prophet_doors/. No site/ artifact, no board, no plan.

Run (nightly / DAG):  python -m scripts.emit_prophet_doors --nightly
Run (safe preview):   python -m scripts.emit_prophet_doors --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import prophet_doors as pd_doors  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nightly", action="store_true",
                    help="forward-advance the door ledger (the SOLE advancer; DAG entry point)")
    ap.add_argument("--dry-run", action="store_true",
                    help="evaluate every door and print what WOULD be flagged; writes nothing")
    ap.add_argument("--json", action="store_true",
                    help="dump the full run document as JSON instead of the text summary")
    args = ap.parse_args()

    # No --nightly => no forward advance, exactly like the sibling ledgers.
    run = pd_doors.emit(dry_run=bool(args.dry_run or not args.nightly))

    if args.json:
        print(json.dumps(run, indent=2, ensure_ascii=False, default=str))
        return

    src = run.get("theme_source") or {}
    print(f"prophet_doors asof={run.get('asof')} universe={run.get('n_universe')} "
          f"runtime={run.get('runtime_s')}s dry_run={run.get('dry_run')}")
    print(f"  theme source: ok={src.get('ok')} asof={src.get('asof')} "
          f"age_days={src.get('age_days')} members={src.get('n_members')}"
          + (f" — {src['reason']}" if src.get("reason") else ""))
    wsrc = run.get("washout_source") or {}
    if wsrc:
        print(f"  washout source: ok={wsrc.get('ok')} universe={wsrc.get('universe_n')} "
              f"evaluated={wsrc.get('evaluated')} skipped={wsrc.get('skipped')} "
              f"| turn={wsrc.get('state_turn')} fresh(<={wsrc.get('fresh_weeks_max')}w)="
              f"{wsrc.get('fresh')} aligned{tuple(wsrc.get('align_grids') or ())}="
              f"{wsrc.get('aligned')} | asof_max={wsrc.get('asof_max')} "
              f"asof_mismatch={wsrc.get('asof_mismatch')} {wsrc.get('runtime_s')}s"
              + (f" — {wsrc['reason']}" if wsrc.get("reason") else ""))
    fsrc = run.get("feature_source") or {}
    if fsrc:
        relay, turn, fore = (fsrc.get(k) or {} for k in ("relay", "turnover", "foresight"))
        print(f"  feature source: relay covered={relay.get('n_covered')}"
              f"/{relay.get('members_indexed')} members"
              + (f" — {relay['reason']}" if relay.get("reason") else "")
              + f" | turnover ok={turn.get('ok')} last={turn.get('last_session')}"
              + (f" — {turn['reason']}" if turn.get("reason") else "")
              + f" | foresight ok={fore.get('ok')} themes={fore.get('n_themes')}"
              + (f" — {fore['reason']}" if fore.get("reason") else ""))
    wfsrc = (run.get("feature_source_w") or {}).get("atlas") or {}
    if wfsrc:
        print(f"  door W feature source: atlas covered={wfsrc.get('n_covered')}"
              f"/{wfsrc.get('n_asked')} flag(s)"
              + (f" — {wfsrc['reason']}" if wfsrc.get("reason") else ""))
    for door in pd_doors.DOORS:
        rows = run["flags"][door]
        print(f"  door {door}: {len(rows)} flag(s)  "
              f"[candidates {run['candidates'][door]}, "
              f"deduped {run['deduped'][door]}, overflow {run['overflow'][door]}]")
        for r in rows:
            f = r["features"]
            if door == pd_doors.DOOR_T:
                print(f"    {r['ticker']:<6} tier={f.get('tier')} ticks={f.get('ticks')} "
                      f"theme=#{f.get('theme_rank')} {f.get('theme')} "
                      f"rs63={f.get('rs63_pctile')} sector={f.get('sector')}")
            elif door == pd_doors.DOOR_R:
                print(f"    {r['ticker']:<6} ticks_since_master={f.get('ticks_since_master')} "
                      f"hist_d2={f.get('hist_d2')} hist_d3={f.get('hist_d3')} "
                      f"k3={f.get('k3')} d3={f.get('d3')} rs63={f.get('rs63_pctile')} "
                      f"sector={f.get('sector')} theme={f.get('theme')}")
            else:
                print(f"    {r['ticker']:<6} since={f.get('since')} "
                      f"weeks={f.get('weeks_since_cross')} "
                      f"depth={f.get('depth_pctile')} "
                      f"(at cross {f.get('depth_pctile_at_cross')}) "
                      f"align={f.get('align_class')} "
                      f"2B={f.get('align_2b')} 3B={f.get('align_3b')} "
                      f"weekly_cb={f.get('weekly_cb')} dd={f.get('drawdown_pct')}% "
                      f"hist={f.get('history_weeks')}w from {f.get('history_start')}")
            # Recorded features (analysis only, prereg §9/§10) — nulls printed, never hidden.
            if door == pd_doors.DOOR_W:
                print(f"      era={f.get('era')} regime={f.get('regime_bucket')} "
                      f"archetype={f.get('archetype')} class={f.get('atlas_class')} "
                      f"(bull @ {f.get('atlas_event_date')}, "
                      f"on_cross={f.get('atlas_event_on_cross')})")
                print(f"      atlas 13w name_post={f.get('atlas_name_post_13w')} "
                      f"(exc {f.get('atlas_name_post_13w_exc')}) "
                      f"arch_post={f.get('atlas_arch_post_13w')} "
                      f"(exc {f.get('atlas_arch_post_13w_exc')})  "
                      f"n=name {f.get('atlas_n_name')}/arch {f.get('atlas_n_archetype')}"
                      f"/global {f.get('atlas_n_global')} "
                      f"(covered={f.get('atlas_covered')})")
            else:
                print(f"      relay_count_3d={f.get('relay_count_3d')} "
                      f"relay_position={f.get('relay_position')} "
                      f"(n={f.get('relay_members_covered')})  "
                      f"turnover_pctile={f.get('turnover_pctile')} "
                      f"(window={f.get('turnover_window')})  "
                      f"foresight_stage={f.get('foresight_stage')} "
                      f"(covered={f.get('foresight_covered')})")
    print(f"  appended to ledger: {run.get('appended')}")


if __name__ == "__main__":
    main()
