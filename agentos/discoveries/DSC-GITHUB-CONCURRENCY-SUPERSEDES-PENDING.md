---
key: GITHUB-CONCURRENCY-SUPERSEDES-PENDING
claim: >
  GitHub Actions concurrency still cancels a PENDING run in a group when a newer
  sibling is scheduled, even when cancel-in-progress is false. The flag only
  protects an already-RUNNING run. Event-conditional cancel-in-progress (the
  fences.yml 2026-08-09 fix) therefore cannot save a queued slot.
falsifier: >
  A queued daily.yml (or fences.yml) run in a shared concurrency group surviving
  a later sibling entering the same group while cancel-in-progress is false —
  GitHub would have to stop replacing the one pending run per group.
so_what: >
  Slots that must not coalesce (daily.yml's EDT cron vs EST-guard; any
  gate-skip sibling of a real bake) need DISTINCT concurrency groups. Do not
  "fix" a queued-run kill by flipping cancel-in-progress; that lever does not
  reach pending-supersede. Actor cancels remain a different class
  (gh_quota_guard shape 6) and cannot see this one.
kind: landmine
verified_at: 2026-08-15
verified_by: >
  gh run view 31848262472 (cancelled, created 2026-08-14T22:52:07Z, updated
  23:45:42Z) and 31851452961 (success, created 23:45:40Z, run_started_at also
  23:45:40Z, et_gate job 02:16:14–02:16:19Z, every other job skipped);
  fences.yml comment 2026-08-09 ("GitHub replaces the one PENDING run per group
  regardless of this flag"); daily.yml cancel-in-progress was already false.
scope: [macro]
confidence: verified
---

## Detail

The 2026-08-14/15 US nightly did not run. The EDT-correct cron sat queued for a
runner and was superseded by the same-group EST-guard slot. The survivor skipped
every real job (wrong regime) and concluded `success`. `cancel-in-progress: false`
was already set; the kill was pending-supersede, not in-progress cancel.
`.claude/hooks/gh_quota_guard.py` shape 6 cannot see GitHub concurrency cancels.
