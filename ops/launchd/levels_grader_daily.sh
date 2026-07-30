#!/bin/sh
# ops/launchd/levels_grader_daily.sh — Voltick Gamma-Levels grading lane
# (launchd label: com.mastermind.levelsgrader, daily 18:00 local).
#
# Mode 1 (backfill): one historical year-chunk per pass, newest→oldest 2026→2017,
#   completed years tracked in data/levels/backfill_done_years.txt. Chunks are safe
#   to re-run: grades.parquet upserts by board_id.
# Mode 2 (maintenance, after all chunks done): rolling 14-day re-grade so newly
#   matured sessions get graded as price bars land.
#
# Env (R2 creds + THETADATA_STORE) comes from run_with_env.sh sourcing .env — this
# script never inlines secrets. Logs via the plist's StandardOutPath.
cd /Users/chriswong/hub-ops-wt || exit 1
PY=/opt/homebrew/Caskroom/miniconda/base/bin/python
STATE=data/levels/backfill_done_years.txt
LOCK=/tmp/mm_levelsgrader.lock

if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
  echo "levelsgrader: previous pass still running (pid $(cat "$LOCK")) — skipping"
  exit 0
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT
mkdir -p data/levels

for Y in 2026 2025 2024 2023 2022 2021 2020 2019 2018 2017; do
  grep -qx "$Y" "$STATE" 2>/dev/null && continue
  echo "levelsgrader: backfill chunk $Y start $(date)"
  "$PY" -m scripts.build_levels_track_record --universe stocks \
      --start "$Y-01-01" --end "$Y-12-31" --publish \
    && echo "$Y" >> "$STATE" \
    && echo "levelsgrader: chunk $Y DONE $(date)"
  exit 0   # one chunk per pass — next pass continues the queue
done

# all chunks done → maintenance: rolling 14-day re-grade
START=$("$PY" -c "from datetime import date,timedelta;print((date.today()-timedelta(days=14)).isoformat())")
echo "levelsgrader: maintenance window $START → now  $(date)"
exec "$PY" -m scripts.build_levels_track_record --universe stocks --start "$START" --publish
