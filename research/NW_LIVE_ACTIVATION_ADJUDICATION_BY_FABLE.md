# NW Live Activation — Codex Docket Adjudication + Master Architecture (by Fable)

Date: 2026-07-06
Status: SHIPPED same-day (all waves merged 2026-07-06)
Source docket: `research/NEURAL_WEB_LIVE_ACTIVATION_RESEARCH_BY_CODEX.md` (Codex, 2026-07-06)
Census: 6-lane verification sweep (cortex / sensors / health / brief / governance / workflow topology), file:line-evidenced, 2026-07-06

## 1. Executive verdict

Codex's docket is directionally right and unusually law-abiding (deterministic
brief, display-only, fail-open, no LLM prose). Verified against the live repo:
4 of 5 lanes BUILD (two substantially improved), 1 lane KEEP (nothing to build —
the locks are already structural). One Codex claim REFUTED, one architectural
hole fixed (two-phase health across the engine/cortex job boundary), one bonus
LETHAL-class hazard closed (silent engine-push failure → cortex deliberates over
stale context, undetected).

## 2. Claim-by-claim adjudication

| Codex claim | Verdict | Evidence |
|---|---|---|
| Cortex tool loop has no provider failover; connection error breaks loop | CONFIRMED | pre-fix cortex.py:1339-1362 — first live provider pinned; llm_auth.make_call waterfall existed but the tool loop bypassed it |
| Cortex degradation encoded "mostly as prose" | REFUTED | memo envelope was already structured (10 fields incl. tool_call_census, probation struct); what was missing was an explicit run_status block + red rendering downstream |
| Job finishes green on a 0-tool-call run | CONFIRMED (live) | committed memo.json 2026-07-06T08:48Z: "Budget exhausted after 0 tool-call batches", census {}; admin displayed census with no alert condition; committee.html silently hid the empty census section |
| build_bottom_sensors unwired while synapse claims daily-engine cadence | CONFIRMED | script docstring self-declared NOT wired (benchmark gate ≤30s never resolved); artifact as_of=2026-07-02 vs 30h SLA |
| No unified NW health artifact | CONFIRMED | admin/neural_web.py computed SLA freshness in-memory across the full registry, nothing durable |
| No canonical NW daily brief | CONFIRMED | build_aibrief (LLM macro brief) and build_briefing (Mastermind ticker triage) are different surfaces; no collision |
| health.json (engine job) can carry same-day cortex status | REFUTED AS SPECCED | cortex is a separate job (needs: engine) running AFTER the engine commit with its own narrow commit lane — Codex's single-phase health would carry yesterday's cortex forever; fixed with the two-phase design (RUL-LIVE6) |
| Promotion locks must hold | KEEP — already structural | kernel_decisions.json: survivors=[], next_batch_due=2026-10-01, standing_law field; cortex probation granted=false, n=0 < min_n=25, Wilson-LB law |

## 3. Master architecture: the NW Live Operating Layer

Six organs; all display/ops-tier; zero new trading authority.

1. **Honest cortex** (#1625): provider failover through the llm_auth waterfall
   (401/403 → mark_dead + next provider; transient → bounded retry then skip;
   mid-conversation failure → one clean restart on the next provider);
   structured `run_status` block in every memo (status ok|warn|degraded|skipped,
   provider_attempts with error classes, tool-call counts, context_stale);
   single-call fallback is unconditionally `degraded` (review-forced honesty —
   see §5); admin red/amber/green pill + committee.html bilingual degraded
   notice replaces the silent hide. Degrade-never-raise preserved: the cortex
   job still always exits 0 — red is a display state, not a deploy gate.
2. **Sensory refresh** (#1621): build_bottom_sensors wired between world state
   and mastermind context (benchmark gate resolved: **2.29s** ≤ 30s law),
   if: always() fail-soft, dag.yml entry, wiring-conformance test. The
   registry-says-daily/workflow-never-runs-it mismatch class is killed for this
   lobe and detected for all others (organ 3).
3. **Vitals — health.json** (#1631): `data/neuralweb/health.json` +
   `site/neuralwebdata/health.json` (schema neuralweb.health.v1), DERIVED from
   synapse.yml + committed artifacts (no parallel registry), storage-class
   aware (r2 → not_locally_verifiable, never "missing"), cheap row counts
   (envelope sidecars / parquet metadata only — render-budget safe),
   workflow_conformance flags (daily-engine producers must appear in
   daily.yml). **Two-phase (RUL-LIVE6)**: engine job builds the core with
   cortex_source=previous_run; the cortex job re-runs `--refresh-cortex` after
   deliberation and commits exactly the two health paths via its narrow
   allowlist. Admin consumes the artifact; its in-memory computation is
   demoted to fallback-for-older-clones.
4. **Morning report — daily_brief.json** (#1637): deterministic, display-only,
   evidence path on every item; answers: did the brain run / what changed /
   what contradicted / what is stale / what deserves operator attention
   (P1/P2/P3, maintenance-language only). Delta method: compact per-lobe
   snapshot vs `daily_brief_history.jsonl` (as_of-keyed idempotent upsert;
   engine phase writes the brief, cortex `--finalize` phase writes history).
   Contradiction wording law: "no_longer_present", never "resolved". Trading
   verbs blacklisted by test AND scrubbed at runtime from upstream-sourced
   strings (see §5). qi domain structurally excluded (border ruling pending).
5. **Ops surfaces**: committee.html Daily Brief block (client-side fetch,
   bilingual l-en/l-zh, expander, zero render-budget cost) + admin
   _section_daily_brief; legacy memos without run_status render via
   derive-fallback everywhere.
6. **Conformance rails**: wiring tests + health workflow_conformance
   institutionalize the registry/workflow mismatch bug class; the duplicate
   synapse count pin (test_half_lives, drifted 113 vs 168) was de-duplicated to
   floor+membership (#1620) so the remaining single pin can't silently fork.

## 4. Rulings

- **RUL-LIVE1**: Cortex model calls route through the llm_auth waterfall; no
  single-provider pinning; every attempt recorded in
  run_status.provider_attempts with error classes.
- **RUL-LIVE2**: Status taxonomy ok/warn/degraded/skipped. Zero-tool
  deliberation and the single-call fallback are ALWAYS degraded. Staleness-gate
  skip preserves the last good memo and is not red while the last successful
  run is within SLA.
- **RUL-LIVE3**: Fail-open preserved — cortex/health/brief failures never block
  the publish; red is a display state, not a deploy gate.
- **RUL-LIVE4**: Bottom sensors wired display-only; benchmark law ≤30s recorded
  (2.29s measured 2026-07-06); scored_path_surfaces stays [].
- **RUL-LIVE5**: health.json is DERIVED from synapse.yml + committed artifacts —
  no parallel registry; admin consumes it; storage-class aware; row counts via
  sidecar/metadata only on the render path.
- **RUL-LIVE6**: Two-phase finalization — engine job builds health/brief cores
  (cortex marked previous_run); cortex job refreshes the cortex section
  (--refresh-cortex) and finalizes the brief + history (--finalize) via its
  narrow-allowlist commit (RUL-NW1 pattern). History rows are as_of-keyed
  upserts; the engine phase never writes the history ledger.
- **RUL-LIVE7**: The brief is deterministic — no LLM prose, no trading verbs
  (unit blacklist + runtime scrub of upstream-sourced strings), evidence path
  per claim; "no_longer_present" ≠ "resolved".
- **RUL-LIVE8**: context_stale self-detection — cortex flags deliberation over
  a world_state older than the run date (silent engine-push-failure detector;
  the push loop is best-effort 5-attempt by design); surfaces as warn + P1
  operator attention.
- **RUL-LIVE9**: No new authority anywhere: health tier=infrastructure, brief
  tier=display, weights none everywhere; kernel FDR lock (2026-10-01,
  structural in kernel_decisions.json) and cortex A2 earn-in (n≥25 graded
  attention events, hits≥8, Wilson-LB) untouched.

## 5. Shipped + review value log

| PR | Content | Opus review outcome |
|---|---|---|
| #1620 | test_half_lives duplicate synapse count pin → floor+membership | (main-loop fix; both pin tests were failing on main) |
| #1625 | PR-A cortex honesty | 1 MUST-FIX: single-call fallback stamped degraded:false/status:warn — the exact "lie to the operator" class this program kills. Fixed + new test. |
| #1621 | PR-B sensor wiring (benchmark 2.29s) | Clean APPROVE. |
| #1631 | PR-C health artifact | 1 MUST-FIX: dag-conformance is a per-job gate — the cortex-lane --refresh-cortex invocation was undeclared and would have redded CI at merge. Fixed. |
| #1637 | PR-D daily brief | 1 MUST-FIX: upstream contradiction descriptions passed through verbatim (trading-verb leak; the scrub guard was dead code — reviewer built a live repro). Fixed: redact-and-log scrub on all dynamically-sourced strings + adversarial test. |
| this PR | docket copy + adjudication + masterplan §11 | — |

## 6. Definition of live (acceptance, first full nightly after 2026-07-06)

- site/neuralwebdata/health.json + daily_brief.json produced today; every major
  lobe has a status; stale/missing named; bottom sensors fresh or honestly
  stale/partial; cortex ok-with-tool-calls or degraded-with-provider-evidence;
  committee/admin render the answer without engine code; no new trading
  authority.
- Post-nightly checks:
  - `curl -fsS https://mastermind-x.com/neuralwebdata/health.json | jq '.overall_status, .summary_counts'`
  - `curl -fsS https://mastermind-x.com/neuralwebdata/daily_brief.json | jq '.status, .did_the_brain_run'`
  - `curl -fsS https://mastermind-x.com/neuralwebdata/bottom_sensors.json | jq '.as_of, .n_rows'`
- Known open ops item (pre-existing, now VISIBLE instead of silent): the cortex
  provider connection failure observed 2026-07-06 (OAuth connection error +
  empty ANTHROPIC_API_KEY in the job env) is an operator credential/network
  fix on the Mac Studio runner. Until fixed, the first nightlies will honestly
  report cortex degraded with provider_attempts evidence — which is the point.
