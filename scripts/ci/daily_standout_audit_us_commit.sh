#!/usr/bin/env bash
# EXTRACTED-VERBATIM-FROM: .github/workflows/daily.yml
# job `standout_audit_us`, step `commit standout audit US artifacts`.
# 2026-08-12 512KB processing-cap diet (tests/test_workflow_file_size.py).
# Env comes from the step's `env:` block, which stays in the YAML.
# Invoked as: bash scripts/ci/daily_standout_audit_us_commit.sh
set -e  # mirror GitHub's default `bash -e {0}` step shell — daily.yml declares no shell:

. "${GITHUB_WORKSPACE:-.}/scripts/ci/push_retry.sh"
git config user.name "dashboard-bot"
git config user.email "actions@users.noreply.github.com"
git add data/standout_audit/us_attribution.parquet 2>/dev/null || true
git add data/standout_audit/us_evidence.jsonl 2>/dev/null || true
git add data/standout_audit/us_audit_state.json 2>/dev/null || true
git add data/standout_audit/pick_autopsies/us 2>/dev/null || true
git add site/factordata/us_audit_scoreboard.json 2>/dev/null || true
git add data/metabolism/fitness/standouts_us.json 2>/dev/null || true
git add site/factordata/us_track_history.json 2>/dev/null || true
git add site/us_track_record.html 2>/dev/null || true
git add data/neuralweb/prophet_status.json 2>/dev/null || true
git add data/neuralweb/prophet_suggestions.json 2>/dev/null || true
git add data/neuralweb/marketing_state.json 2>/dev/null || true
git add site/neuralwebdata/marketing_lobe.json 2>/dev/null || true
git add data/marketing/sentinel_report.json 2>/dev/null || true
git add data/marketing/content_plan.json 2>/dev/null || true
git add data/marketing/hot_tape_pack.json 2>/dev/null || true
git add data/marketing/cashtag_tiers.json 2>/dev/null || true
git add data/marketing/radar_report.json 2>/dev/null || true
git add data/marketing/opportunities.jsonl 2>/dev/null || true
git add data/marketing/radar_plan_history.json 2>/dev/null || true
git add data/marketing/outbox 2>/dev/null || true
# Ad Central arena ledgers — forward-only, advanced by the ingest step above.
git add data/marketing/ad_central 2>/dev/null || true
# Persona memory ledgers (XG-W3) — forward-only, advanced by the
# consolidate step above. The host spool (data/marketing/personas_host/)
# is gitignored and must never appear here.
git add data/marketing/personas 2>/dev/null || true
# THE MARKETING LANES' AI SPEND AND RUNG HEALTH (W2, 2026-08-08).
# Every marketing LLM lane already books an ai_costs row per served
# call (engine/llm_auth._capture_usage, usage_lane=marketing-*) and
# NOTHING IN THIS JOB EVER STAGED THEM: the two jobs whose broad
# `git add data/` sweeps usage.jsonl in are `engine:` and asia-close's
# `asia:`, so the marketing rows were written to this job's checkout
# and then discarded by the next actions/checkout. The committed
# ledger consequently held 3,372 rows on 2026-08-08 with ZERO from any
# marketing lane, which read as "the copywriter books no usage" and is
# in fact "the copywriter's usage is never committed". Same reason for
# provider_health.jsonl, the new per-rung ledger: an artifact nobody
# commits cannot answer a question a week later.
git add data/ai_costs 2>/dev/null || true
if git diff --cached --quiet; then echo "no standout audit US changes"; exit 0; fi
# Fail-closed conflict gate (P0 d29e4dd44d/#4167): the marketing
# learning push above runs while these paths sit dirty — if its pull
# machinery ever regresses to a conflicted autostash apply, this add
# would stage the markers. Heal display paths, die on ledger paths.
push_staged_heal data/ site/ || exit 1
if git diff --cached --quiet; then echo "no standout audit US changes after conflict heal"; exit 0; fi
git commit -m "standout-audit-us: nightly US attribution + fitness card $(date -u +%F)"
# best-effort rebase-push (own files — no other job writes these paths)
PUSH_ALARM=420
push_retry_init "standout audit US artifacts"
while push_attempt; do
  perl -e 'alarm 120; exec @ARGV or die' -- git fetch origin main || true
  comm -12 <(git ls-files --others --exclude-standard | LC_ALL=C sort) \
           <(git ls-tree -r --name-only origin/main | LC_ALL=C sort) \
    | while IFS= read -r f; do rm -f -- "$f" || true; done
  if perl -e 'alarm 420; exec @ARGV or die' -- git pull --rebase --autostash -X theirs origin main && push_autostash_ok; then
    if push_do; then echo "pushed standout audit US artifacts on attempt $PUSH_ATTEMPT"; push_won; exit 0; fi
  fi
  push_abort_rebase
  push_backoff
done
push_lost
echo "::warning::could not push standout audit US artifacts after $PUSH_ATTEMPT attempts ($PUSH_STOP) (non-fatal)"
