# Post-#3574 rebase playbook (main-loop checklist)

PR #3574 (brain run-registry: app/brain_runs.py + widget turn objects) merges before us.
After both builders return and #3574 is merged:

1. `git fetch origin && git merge origin/main` on this worktree branch.
2. Expected conflict map:
   - `engine/neuralweb/brain_gateway.py` — LOW: #3574 adds user-turn persistence at step 4
     (after `_load_thread_history`) and slims step 7 to assistant-only. Our edits live in
     helpers + `_run_brain_loop_stream` + lane-provider builder + chat/chat_stream param
     threading. Take BOTH (theirs at step 4/7, ours elsewhere).
   - `app/main.py` — ours untouched (builder was re-scoped): take theirs wholesale.
   - `tests/test_brain_sse_keepalive.py` — take theirs (run-registry rewrite); we add no
     keepalive tests (B7 revised).
   - `tests/test_brain_gateway.py` — union both test additions.
   - `templates/mm_brain.js` + `site/mm_brain.js` — HEAVY: take #3574's structure as base,
     re-apply the timeline module + its integration sites onto the new shape:
       • holder: hang the timeline state off `T` in `newTurn` (T.tl), typing bubble is the
         `typing` param.
       • `handleEvent(j, T)`: add `status` branch (must reach shared `return true` tail —
         cursor law) + upgrade `tool` branch to prefer label_en/label_zh (+detail), fallback
         generic label, NEVER raw name; `delta` branch → collapse timeline to summary chip;
         `finalizeDone` → teardown (chip stays); `failTurn`/`stopStream`/`shelve` → teardown.
       • replayed status events on re-attach fast-forward the timeline (fine by design);
         chip elapsed uses client clock from turn start (undercounts on resume — accepted).
   - `site/chat.html` + `templates/chat.html` — theirs only.
3. Re-run: full test gate (§0.1 list + tests/test_brain_runs.py) + `python -m
   scripts.check_template_site_sync --fix` + `node --check` both mm_brain copies +
   `cmp` the pair.
4. Preview-verify the widget harness (research/mastermind_transparency_latency/
   widget_harness.html) + screenshot for the PR body.
5. Opus reviewer pass on the FULL merged diff (leak-safety greps: no raw tool names/params
   on the wire; cursor law; fail-open failover; cache_control constants not mutated;
   deepseek-only thinking param; quota paths untouched).
6. Ship: commit → push → PR (body from PR_BODY_DRAFT.md + harness screenshots) → CI →
   same-day squash-merge → VPS `git reset --hard origin/main` + `systemctl restart
   macro-api` (update.sh gate may not cover brain.yml) → live verify:
   a. `curl -s "https://www.mastermind-x.com/mm_brain.js?cb=$RANDOM" | grep -c mmb-think`
      (new widget live at edge),
   b. timed SSE probe (scratchpad sse_time.py): expect meta ≤1s, first status <1.5s,
      status cadence ≤ every few s, delta total: fast ≤12s typical,
   c. `journalctl -u macro-api` — pro turn shows ≤1 cooling-probe 429 then degraded serve,
   d. https://mastermind-x.com/api/health sha == merged sha.
