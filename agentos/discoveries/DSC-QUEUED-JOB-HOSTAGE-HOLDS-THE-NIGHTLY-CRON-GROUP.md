---
key: QUEUED-JOB-HOSTAGE-HOLDS-THE-NIGHTLY-CRON-GROUP
claim: >
  A workflow job whose runs-on label is carried by NO live runner queues forever;
  GitHub only kills a queued job after 24h. Until then its RUN stays alive, an
  alive scheduled run holds its per-cron concurrency group, and the next night's
  scheduled run sits `pending` with ZERO jobs created until the predecessor's
  queued job dies — so a single orphaned label converts the sole authoritative
  nightly into a self-perpetuating cascade that starts ~3-6h later each night
  with no red anywhere. Labels added via the runners API live only in API state:
  nothing in the repo pins them, so deregistering a host silently orphans every
  label it carried (theta-m1 died with mac-builder-1/2; collect_tail was
  unschedulable from ~08-15).
falsifier: >
  A daily.yml run with a queued-forever job whose concurrency group frees before
  that job's 24h kill (would mean queued jobs do not hold the group), or GitHub
  scheduling a job onto a runner that lacks one of its runs-on labels, or a
  checked-in registry that fails CI when a workflow references a label absent
  from the live pool (would close the orphaned-label class at PR time).
so_what: >
  When the nightly is pending with zero jobs, look for an OLDER sibling run held
  alive by a queued job, and check that job's runs-on label against
  `gh api repos/{o}/{r}/actions/runners` before diagnosing anything else. The
  triage lever is restoring the label onto a live runner (reversible, instant
  assignment) — never cancelling the run (operator-only). Durable fixes shipped
  2026-08-17: collect_tail unpinned to macstudio, liveness IN_FLIGHT_MAX_AGE,
  rescue §0.4a wedge amendment (DEC:PROPHET-NIGHTLY-WEDGE-HARDENING).
kind: landmine
verified_at: 2026-08-17
verified_by: >
  gh run view 31977372592 --json status,jobs (status=queued 25h after creation,
  17/19 jobs completed, collect_tail queued since 06:07:55Z on theta-m1 which
  `gh api repos/{o}/{r}/actions/runners` showed on zero runners); run
  32077948964 pending, total_count 0 jobs, in group pipeline-daily-3-cron-30 22;
  label restore POST /actions/runners/35/labels at 23:47Z → collect_tail
  assigned to mac-builder-3 within minutes. Full chain:
  research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md.
scope: [macro]
confidence: verified
---

The 2026-08-14→17 Prophet freeze's scheduling half. The Aug-15 run held its
group until 08-17 02:35Z (collect_tail's 24h kill), the Aug-16 run until the
label restore; each night's bake started hours later than the last. GitHub's
24h queued-job kill is the ONLY native escape, and it re-arms nightly because
the next run mints its own hostage. See the postmortem for the detection-side
holes this exposed (liveness in-flight INDETERMINATE without an age cap,
rescue §0.4a reading a hostage as a live bake).
