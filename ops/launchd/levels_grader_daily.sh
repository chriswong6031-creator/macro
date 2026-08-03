#!/bin/sh
# ops/launchd/levels_grader_daily.sh — Voltick Gamma-Levels grading lane
# (launchd label: com.mastermind.levelsgrader, daily 18:00 local).
#
# Mode 0 (always): refresh data/levels/index_bars (SPY/QQQ/IWM/DIA + ^GSPC for
#   SPX/SPXW) — the R2.4b index lane's price store. Non-fatal.
# Mode 1a (index backfill, R2.4b): one historical year-chunk per pass for the six
#   index anchor roots, newest→oldest, tracked in backfill_done_years_index.txt.
#   Runs BEFORE the stocks queue — the flagship roots drain in ~10 passes. Index
#   runs never --publish: the R2 levels_track_record.json is a latest-run artifact
#   and must keep reflecting the stocks universe; index results reach consumers
#   through grades.parquet → the per-root level_grades scorecards.
# Mode 1b (stocks backfill): one year-chunk per pass, 2026→2017, tracked in
#   data/levels/backfill_done_years.txt. Chunks are safe to re-run: grades.parquet
#   upserts by board_id.
# Mode 2 (maintenance, after both queues drain): rolling 14-day re-grade of BOTH
#   universes so newly matured sessions get graded as price bars land.
#
# Env (R2 creds + THETADATA_STORE) comes from run_with_env.sh sourcing .env — this
# script never inlines secrets. Logs via the plist's StandardOutPath.
cd /Users/chriswong/hub-ops-wt || exit 1
PY=/opt/homebrew/Caskroom/miniconda/base/bin/python
STATE=data/levels/backfill_done_years.txt
STATE_IX=data/levels/backfill_done_years_index.txt
LOCK=/tmp/mm_levelsgrader.lock

if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
  echo "levelsgrader: previous pass still running (pid $(cat "$LOCK")) — skipping"
  exit 0
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT
mkdir -p data/levels

# R2.4b: keep the index-root bar store fresh. A Yahoo outage just grades fewer
# index boards tonight — never fatal.
"$PY" -m scripts.refresh_index_bars \
  || echo "levelsgrader: index-bars refresh failed (non-fatal)"

# R2.4b index lane first (see Mode 1a above: no --publish by design).
for Y in 2026 2025 2024 2023 2022 2021 2020 2019 2018 2017; do
  grep -qx "$Y" "$STATE_IX" 2>/dev/null && continue
  echo "levelsgrader: INDEX backfill chunk $Y start $(date)"
  "$PY" -m scripts.build_levels_track_record --universe index \
      --start "$Y-01-01" --end "$Y-12-31" \
    && echo "$Y" >> "$STATE_IX" \
    && echo "levelsgrader: index chunk $Y DONE $(date)"
  "$PY" -m scripts.build_level_grades_summary \
    || echo "levelsgrader: scorecard publish failed (non-fatal)"
  exit 0   # one chunk per pass — next pass continues the queue
done

for Y in 2026 2025 2024 2023 2022 2021 2020 2019 2018 2017; do
  grep -qx "$Y" "$STATE" 2>/dev/null && continue
  echo "levelsgrader: backfill chunk $Y start $(date)"
  "$PY" -m scripts.build_levels_track_record --universe stocks \
      --start "$Y-01-01" --end "$Y-12-31" --publish \
    && echo "$Y" >> "$STATE" \
    && echo "levelsgrader: chunk $Y DONE $(date)"
  # R2.4: refresh the live scorecards from whatever is graded so far (non-fatal).
  "$PY" -m scripts.build_level_grades_summary \
    || echo "levelsgrader: scorecard publish failed (non-fatal)"
  exit 0   # one chunk per pass — next pass continues the queue
done

# all chunks done → maintenance: rolling 14-day re-grade (index lane unpublished
# by design — see Mode 1a), then the R2.4 scorecards
START=$("$PY" -c "from datetime import date,timedelta;print((date.today()-timedelta(days=14)).isoformat())")
echo "levelsgrader: maintenance window $START → now  $(date)"
"$PY" -m scripts.build_levels_track_record --universe index --start "$START" \
  || echo "levelsgrader: index maintenance pass failed (non-fatal)"
"$PY" -m scripts.build_levels_track_record --universe stocks --start "$START" --publish
rc=$?
echo "levelsgrader: track-record pass exit=$rc — publishing level-grade scorecards $(date)"
"$PY" -m scripts.build_level_grades_summary \
  || echo "levelsgrader: scorecard publish failed (non-fatal)"
exit $rc
