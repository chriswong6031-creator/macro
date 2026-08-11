<!-- GENERATED — do not edit by hand; regenerate with `python -m scripts.build_project_active_build_map`. Advisory only; gates nothing. -->

# Project Active Build Map

Project-wide coordination view for exactly Macro, Terminal, and Mastermind. Macro's deeper repository-local map remains `docs/ACTIVE_BUILD_MAP.md`.

Collected: 2026-08-11T13:24:20.082810+00:00  |  Open PRs: 14  |  Conflicts: 1  |  File collisions: 6

## Repositories

| Repository | Base | SHA | Open | Conflicts | Protected PRs | Dependencies | Collisions | Recently merged |
|------------|------|-----|------|-----------|---------------|--------------|------------|-----------------|
| `mastermindx-market-intelligence/macro` | `main` | `2585bf41b883` | 10 | 1 | 6 | 0 | 6 | 50 |
| `mastermindx-market-intelligence/mastermind-terminal` | `master` | `eb5216452d17` | 3 | 0 | 0 | 1 | 0 | 50 |
| `mastermindx-market-intelligence/Mastermind` | `master` | `26b31066f4a8` | 1 | 0 | 1 | 0 | 0 | 16 |

## Open Pull Requests

| Repository | PR | Title | Branch | Updated | Draft | Conflict | Files | Protected paths | Dependencies |
|------------|----|-------|--------|---------|-------|----------|-------|-----------------|--------------|
| `macro` | [#5340](https://github.com/mastermindx-market-intelligence/macro/pull/5340) | deploy: repoint terminal-data-setup's repo URL comment to the org | `claude/org-migration-refs` | 2026-08-11T13:20:48Z | no | no | 1 | `app/deploy/terminal-data-setup.sh` | — |
| `macro` | [#5345](https://github.com/mastermindx-market-intelligence/macro/pull/5345) | ops: add private project runtime truth | `codex/runtime-truth-manifest-20260811` | 2026-08-11T13:19:54Z | no | no | 14 | `.github/ci/legacy-jobs.yml`, `.github/workflows/ci.yml`, `app/deploy/update.sh` | — |
| `macro` | [#5339](https://github.com/mastermindx-market-intelligence/macro/pull/5339) | research(prophet-us): early-admission construction bake-off — §6.8(a)/(b) replays + stop-anchored ruler | `claude/prophet-us-early-admission-bakeoff` | 2026-08-11T13:17:12Z | no | no | 6 | — | — |
| `macro` | [#5334](https://github.com/mastermindx-market-intelligence/macro/pull/5334) | topa-w2: tier-widening wave — B2 confirms cross-tier, A4 reverses, F1/F3/B3 ore body replicates 4/4 panels (G0.5 PRESENTABLE) | `claude/topa-w2-tier-widening` | 2026-08-11T13:13:23Z | no | no | 8 | — | — |
| `macro` | [#5336](https://github.com/mastermindx-market-intelligence/macro/pull/5336) | feat(biocatalyst): arm bounded family clocks | `claude/biocatalyst-forward-clock-20260811` | 2026-08-11T13:11:02Z | no | no | 13 | — | — |
| `macro` | [#5343](https://github.com/mastermindx-market-intelligence/macro/pull/5343) | gmi(w1b): theme-graph semantic spine — bitemporal nodes/edges/evidence + crosswalk CN family + seeder shape discrimination + CN limit-rule registry | `claude/gmi-w1b-theme-graph-spine` | 2026-08-11T13:09:06Z | no | no | 35 | `.github/ci/legacy-jobs.yml`, `.github/workflows/daily.yml`, `config/dag.yml`, `config/synapse.yml` +2 more | — |
| `macro` | [#5338](https://github.com/mastermindx-market-intelligence/macro/pull/5338) | fix(nightly): make engine output loss fail closed | `claude/nightly-output-publication-repair-20260810` | 2026-08-11T13:07:29Z | no | no | 2 | `.github/workflows/daily.yml` | — |
| `macro` | [#5344](https://github.com/mastermindx-market-intelligence/macro/pull/5344) | fix(prophet): make marks schedule timezone neutral | `codex/prophet-marks-et-scheduler-20260811` | 2026-08-11T13:00:25Z | yes | no | 3 | — | — |
| `macro` | [#5331](https://github.com/mastermindx-market-intelligence/macro/pull/5331) | tests(govrev): clamp vintage-derived negative clock offsets above the newest source instant | `claude/govrev-fixture-margin-clamp` | 2026-08-11T12:53:21Z | no | no | 4 | `.github/ci/legacy-jobs.yml` | — |
| `macro` | [#5333](https://github.com/mastermindx-market-intelligence/macro/pull/5333) | fix(price-pressure): cold-runner store restore + R2-canonical event ledger (successor to #5322) | `claude/pressure-ledger-r2b` | 2026-08-11T10:54:45Z | no | yes | 12 | `.github/workflows/daily.yml`, `config/dag.yml`, `config/synapse.yml`, `docs/SIGNAL_BUS.md` | — |
| `terminal` | [#397](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/397) | fix(alerts): evaluate options against live sources | `claude/live-options-alert-sources-20260811` | 2026-08-11T13:19:12Z | yes | no | 12 | — | — |
| `terminal` | [#396](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/396) | fix(flow): show measured source freshness truth | `codex/flow-freshness-truth-20260811` | 2026-08-11T12:45:21Z | yes | no | 16 | — | — |
| `terminal` | [#370](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/370) | fix(financials): one normalization point for every income surface, HK reporting style verified, vendor sort off a null column | `claude/fin-followups-364` | 2026-08-09T03:38:34Z | no | no | 10 | — | `mastermindx-market-intelligence/mastermind-terminal#364` (recently_merged) |
| `mastermind` | [#15](https://github.com/mastermindx-market-intelligence/Mastermind/pull/15) | Rebuild Mastermind portfolio brains and archive legacy US boards | `codex/us-brain-rebuild-019fe4e5` | 2026-08-11T13:22:55Z | no | no | 100+ (truncated) | `.github/workflows/ci.yml`, `bridge/macro_snapshot.py`, `config/agents.yml`, `config/authority_map.yml` +4 more | — |

**Incomplete file census:** GitHub capped changed-file results for `mastermind#15`. Their protected-path lists and all collision negatives are indeterminate beyond the fetched files.

## File Collisions

| Repository | PR A | PR B | Shared files | Protected collision |
|------------|------|------|--------------|---------------------|
| `mastermindx-market-intelligence/macro` | #5333 | #5343 | `.github/workflows/daily.yml`, `config/dag.yml`, `config/synapse.yml`, `docs/SIGNAL_BUS.md` | yes |
| `mastermindx-market-intelligence/macro` | #5331 | #5343 | `.github/ci/legacy-jobs.yml` | yes |
| `mastermindx-market-intelligence/macro` | #5331 | #5345 | `.github/ci/legacy-jobs.yml` | yes |
| `mastermindx-market-intelligence/macro` | #5333 | #5338 | `.github/workflows/daily.yml` | yes |
| `mastermindx-market-intelligence/macro` | #5338 | #5343 | `.github/workflows/daily.yml` | yes |
| `mastermindx-market-intelligence/macro` | #5343 | #5345 | `.github/ci/legacy-jobs.yml` | yes |
_Collision coverage is incomplete for the truncated repository or file censuses named above._

## Recently Merged (last 14 days)

| Repository | PR | Title | Branch | Merged |
|------------|----|-------|--------|--------|
| `macro` | [#5342](https://github.com/mastermindx-market-intelligence/macro/pull/5342) | Flow: publish source-clock and cadence truth | `codex/flow-cadence-truth-20260811` | 2026-08-11T13:05:38Z |
| `macro` | [#5341](https://github.com/mastermindx-market-intelligence/macro/pull/5341) | fix(prophet): run marks publisher from deployed checkout | `codex/prophet-marks-runner-root-20260811` | 2026-08-11T12:50:35Z |
| `macro` | [#5335](https://github.com/mastermindx-market-intelligence/macro/pull/5335) | Let the main integration baseline finish checkout | `codex/integration-baseline-checkout-timeout-20260811` | 2026-08-11T11:55:56Z |
| `macro` | [#5337](https://github.com/mastermindx-market-intelligence/macro/pull/5337) | gmi(w1a): revive THS PIT snapshot cadence + US membership snapshots + freshness tripwire + 42-organ disposition sweep | `claude/gmi-w1a-ths-pit` | 2026-08-11T11:44:10Z |
| `macro` | [#5332](https://github.com/mastermindx-market-intelligence/macro/pull/5332) | options: add frozen campaign cohort ledger | `codex/options-signal-campaign-20260811` | 2026-08-11T10:34:04Z |
| `macro` | [#5305](https://github.com/mastermindx-market-intelligence/macro/pull/5305) | prophet(us): force-majeure outage backfill — receipt-exact 2026-08-09 replay (rev-1, supersedes #5294) | `claude/prophet-outage-backfill-repin-verified` | 2026-08-11T10:01:36Z |
| `macro` | [#5327](https://github.com/mastermindx-market-intelligence/macro/pull/5327) | dag: declare every daily.yml fetch_r2 re-invocation; red vanished re-invocations in the conformance differ | `claude/dag-fetch-r2-declarations` | 2026-08-11T09:57:52Z |
| `macro` | [#5320](https://github.com/mastermindx-market-intelligence/macro/pull/5320) | merge-on-green: a fresh red must always leave a visible marker (#5291) | `claude/mog-red-leaves-a-marker` | 2026-08-11T09:56:25Z |
| `macro` | [#5307](https://github.com/mastermindx-market-intelligence/macro/pull/5307) | fix(us-board): anchor the display-tier earnings chip to the board session (host-clock determinism) | `claude/eb-chip-session-anchor` | 2026-08-11T09:52:54Z |
| `macro` | [#5319](https://github.com/mastermindx-market-intelligence/macro/pull/5319) | feat(massive_stock_day): refuse local research reads of a stale mirror | `claude/massive-local-staleness-tripwire` | 2026-08-11T09:49:35Z |
| `macro` | [#5301](https://github.com/mastermindx-market-intelligence/macro/pull/5301) | prophet(us): plain-word disclosure for reconstructed plans (chip + receipt + footnote, EN/ZH) | `claude/prophet-reconstructed-disclosure` | 2026-08-11T09:42:43Z |
| `macro` | [#5304](https://github.com/mastermindx-market-intelligence/macro/pull/5304) | docs(prophet-us): backfill design rev-1 — restore review-corrected input adjudication | `claude/prophet-backfill-design-rev1` | 2026-08-11T09:38:09Z |
| `macro` | [#5306](https://github.com/mastermindx-market-intelligence/macro/pull/5306) | marketing: posting outbids telemetry — single-fire the metrics poll, cap it at 8 calls | `claude/metrics-poll-rationing` | 2026-08-11T09:38:00Z |
| `macro` | [#5308](https://github.com/mastermindx-market-intelligence/macro/pull/5308) | docs(calcbench): Wave 0B handoff — the blocker is four secrets, not the pipeline | `claude/calcbench-wave0b-handoff` | 2026-08-11T09:37:45Z |
| `macro` | [#5310](https://github.com/mastermindx-market-intelligence/macro/pull/5310) | docs(biocatalyst): return handoff to Codex — what is done, what is not, and one correction | `claude/bio-handoff-to-codex` | 2026-08-11T09:37:39Z |
| `macro` | [#5328](https://github.com/mastermindx-market-intelligence/macro/pull/5328) | BioCatalyst: add governed Capital Structure PIT adapter | `claude/biocatalyst-c2-20260811` | 2026-08-11T09:37:32Z |
| `macro` | [#5329](https://github.com/mastermindx-market-intelligence/macro/pull/5329) | Publish durable opportunity receipts for Terminal | `claude/opportunity-timeline-20260810` | 2026-08-11T09:37:25Z |
| `macro` | [#5326](https://github.com/mastermindx-market-intelligence/macro/pull/5326) | GMI Theme Graph W0 — phase-0 adjudication masterplan (next TIL chapter: rail + waves, not a lobe) | `claude/gmi-theme-graph-w0` | 2026-08-11T09:35:35Z |
| `macro` | [#5330](https://github.com/mastermindx-market-intelligence/macro/pull/5330) | Add fail-closed Market Memory promotion audit | `codex/market-memory-w7-promotion-audit-20260811` | 2026-08-11T09:10:54Z |
| `macro` | [#5321](https://github.com/mastermindx-market-intelligence/macro/pull/5321) | Release Radar: add coherent CPI truth substrate | `codex/release-radar-coherent-target-wave2-20260810` | 2026-08-11T08:22:57Z |
| `macro` | [#5324](https://github.com/mastermindx-market-intelligence/macro/pull/5324) | feat(options): durably land PIT episode evidence | `codex/options-episode-durable-landing-20260811-v2` | 2026-08-11T08:00:33Z |
| `macro` | [#5325](https://github.com/mastermindx-market-intelligence/macro/pull/5325) | Add the proposed-only Market Memory research handoff | `codex/market-memory-w6a-rf-adapter-20260811` | 2026-08-11T07:54:48Z |
| `macro` | [#5315](https://github.com/mastermindx-market-intelligence/macro/pull/5315) | feat(options): add PIT per-side PRISM unusual lens | `codex/momoedge-prism-unusual-20260810` | 2026-08-11T07:21:28Z |
| `macro` | [#5312](https://github.com/mastermindx-market-intelligence/macro/pull/5312) | Add the synthetic Operating Cortex conformance layer | `codex/market-memory-w5a-cortex-20260810` | 2026-08-11T06:44:57Z |
| `macro` | [#5311](https://github.com/mastermindx-market-intelligence/macro/pull/5311) | fix(biocatalyst): publish across sandbox mount boundary | `claude/biocatalyst-completion-20260810` | 2026-08-11T06:42:00Z |
| `macro` | [#5316](https://github.com/mastermindx-market-intelligence/macro/pull/5316) | Make US Prophet copy human and keep earnings setups visible | `claude/us-prophet-human-copy-20260810` | 2026-08-11T06:38:58Z |
| `macro` | [#5298](https://github.com/mastermindx-market-intelligence/macro/pull/5298) | feat(winner-health): W1 display surface — nightly maturation states + Winner Health page (TOPA) | `claude/top-anatomy-w1-winner-health` | 2026-08-11T06:10:01Z |
| `macro` | [#5300](https://github.com/mastermindx-market-intelligence/macro/pull/5300) | docs(topa): primary-checkout massive_stock_day mirror is frozen — fetch_r2 before local passes | `docs/massive-mirror-staleness-topa` | 2026-08-11T06:07:23Z |
| `macro` | [#5297](https://github.com/mastermindx-market-intelligence/macro/pull/5297) | research(top-anatomy): phase-0 results — reconciled instrument, run-3 headline + repair/cross-check arms | `claude/top-anatomy-p0-results` | 2026-08-11T06:06:08Z |
| `macro` | [#5318](https://github.com/mastermindx-market-intelligence/macro/pull/5318) | test(us-board): repair rendered-fixture CI drift | `claude/us-board-basing-gate-20260810` | 2026-08-11T06:05:16Z |
| `macro` | [#5313](https://github.com/mastermindx-market-intelligence/macro/pull/5313) | Refine Macro release-detail modal | `codex/refine-macro-release-modal-20260810` | 2026-08-11T05:59:06Z |
| `macro` | [#5314](https://github.com/mastermindx-market-intelligence/macro/pull/5314) | Register the US candidate-pool contract disclosure | `codex/us-candidate-pool-contract-drift-20260811` | 2026-08-11T04:34:00Z |
| `macro` | [#5309](https://github.com/mastermindx-market-intelligence/macro/pull/5309) | feat: add synthetic episodic retrieval conformance | `codex/market-memory-w4a-retrieval-20260811T000948Z` | 2026-08-11T04:15:40Z |
| `macro` | [#5299](https://github.com/mastermindx-market-intelligence/macro/pull/5299) | test: decouple breadth fixtures from nightly tip | `codex/market-memory-breadth-fixture-drift-20260810` | 2026-08-11T03:32:11Z |
| `macro` | [#5291](https://github.com/mastermindx-market-intelligence/macro/pull/5291) | marketing voice v5: the read is in the selection, not a performed reaction | `claude/marketing-voice-v5` | 2026-08-11T02:32:52Z |
| `macro` | [#5295](https://github.com/mastermindx-market-intelligence/macro/pull/5295) | prophet(us): lossless candidate-pool lanes + dated pool store (CN-parity, display-tier) | `prophet-us-candidate-pool-lanes` | 2026-08-11T02:29:39Z |
| `macro` | [#5292](https://github.com/mastermindx-market-intelligence/macro/pull/5292) | feat(price-pressure): §10.1 VIXCLS stamp-completion pass + immutable receipts | `claude/pressure-vix-completion` | 2026-08-11T02:19:53Z |
| `macro` | [#5296](https://github.com/mastermindx-market-intelligence/macro/pull/5296) | Repair W3 playback catalog store readiness | `codex/market-memory-w3a-live-availability-20260810` | 2026-08-11T02:09:51Z |
| `macro` | [#5289](https://github.com/mastermindx-market-intelligence/macro/pull/5289) | docs(prophet-us): outage backfill design of record (operator force-majeure 2026-08-11) | `claude/prophet-outage-backfill-design` | 2026-08-11T01:14:08Z |
| `macro` | [#5288](https://github.com/mastermindx-market-intelligence/macro/pull/5288) | research: make the R4 prereg PIT-safe and power-honest | `claude/drl-r4-prereg-amendment-2` | 2026-08-11T01:02:03Z |
| `macro` | [#5287](https://github.com/mastermindx-market-intelligence/macro/pull/5287) | marketing: liveness tripwire — a dead publisher can no longer run green | `claude/marketing-liveness-tripwire` | 2026-08-11T00:50:51Z |
| `macro` | [#5286](https://github.com/mastermindx-market-intelligence/macro/pull/5286) | Prepare exact operational playback catalog | `codex/market-memory-w3a-playback-prep-20260810` | 2026-08-11T00:40:27Z |
| `macro` | [#5285](https://github.com/mastermindx-market-intelligence/macro/pull/5285) | research: register R4 VIX-gradient prereg (DRL §8 leg 1) | `claude/drl-r4-vix-prereg` | 2026-08-11T00:24:34Z |
| `macro` | [#5284](https://github.com/mastermindx-market-intelligence/macro/pull/5284) | feat: add synthetic per-event scoring contracts | `codex/market-memory-w2b1-scoring-20260810` | 2026-08-10T23:59:42Z |
| `macro` | [#5283](https://github.com/mastermindx-market-intelligence/macro/pull/5283) | feat: seal private forward evaluation contracts | `codex/market-memory-w2a-forward-contracts-20260810` | 2026-08-10T22:48:09Z |
| `macro` | [#5282](https://github.com/mastermindx-market-intelligence/macro/pull/5282) | fix: harden option OI rollout reconciliation | `codex/market-memory-w1b5-rollout-bridge-20260810` | 2026-08-10T22:15:59Z |
| `macro` | [#5281](https://github.com/mastermindx-market-intelligence/macro/pull/5281) | fix: accept processless systemd timer state | `codex/fix-market-memory-timer-stop-20260810` | 2026-08-10T21:28:43Z |
| `macro` | [#5280](https://github.com/mastermindx-market-intelligence/macro/pull/5280) | fix: unblock private option OI canary deployment | `codex/fix-market-memory-options-dropin-20260810` | 2026-08-10T21:25:34Z |
| `macro` | [#5279](https://github.com/mastermindx-market-intelligence/macro/pull/5279) | feat: add private option OI availability canary | `codex/market-memory-w1b5-options-20260810` | 2026-08-10T21:09:53Z |
| `macro` | [#5278](https://github.com/mastermindx-market-intelligence/macro/pull/5278) | feat(market-memory): add timestamp uncertainty plan | `codex/market-memory-w1b4-uncertainty-20260810` | 2026-08-10T18:38:41Z |
| `macro` | — | _Window truncated at the most recent 50 PRs._ | — | — |
| `terminal` | [#395](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/395) | docs: correct Terminal repository orientation | `claude/readme-orientation-20260811` | 2026-08-11T12:27:27Z |
| `terminal` | [#394](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/394) | org-migration: repoint repo references to the mastermindx-market-intelligence org | `claude/org-migration-refs` | 2026-08-11T11:56:08Z |
| `terminal` | [#393](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/393) | fix(chart): dead-on-load hover — gate ChartPanel's post-touch guards on a touch having happened | `claude/strange-mestorf-0afa1a` | 2026-08-11T10:01:10Z |
| `terminal` | [#392](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/392) | Surface early bottom entries and durable Prophet receipts | `claude/oracle-bottom-entry-20260810` | 2026-08-11T08:52:07Z |
| `terminal` | [#391](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/391) | feat(options): expose exact-side unusual volume receipts | `codex/momoedge-prism-unusual-rail-20260811` | 2026-08-11T07:36:02Z |
| `terminal` | [#390](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/390) | fix(prophet): route SignalCard "vs plan" P&L label through the bilingual string table | `claude/musing-hawking-40957a` | 2026-08-11T06:04:14Z |
| `terminal` | [#388](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/388) | prophet: render reconstruction disclosure from row data (chip + tier-2) | `claude/prophet-origination-disclosure-20260810` | 2026-08-11T05:35:44Z |
| `terminal` | [#389](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/389) | Wire A-share auction price and restore mobile timeframes | `claude/cn-premarket-mobile-timeframes-20260810` | 2026-08-11T04:01:04Z |
| `terminal` | [#387](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/387) | fix(chart): drag-safe premium-suite prim tooltips — hit-tested, pointer-events removed | `claude/indicator-prim-hit-test-20260810` | 2026-08-11T01:26:02Z |
| `terminal` | [#386](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/386) | feat(portfolio): switch existing watchlists | `claude/options-portfolio-watchlists-r5-20260810` | 2026-08-10T20:12:48Z |
| `terminal` | [#385](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/385) | feat(options): add put-call OI history | `claude/options-put-call-history-r5-20260810` | 2026-08-10T19:02:31Z |
| `terminal` | [#384](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/384) | feat(options): add honest 0DTE and largest-event boards | `claude/options-flow-derived-boards-20260810` | 2026-08-10T18:11:21Z |
| `terminal` | [#383](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/383) | feat(options): seven-category R5 information architecture | `claude/options-seven-category-ia-stage-a-20260810` | 2026-08-10T17:14:30Z |
| `terminal` | [#382](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/382) | feat(options): export active screener view to CSV | `claude/options-screener-csv-export-20260810` | 2026-08-10T16:22:15Z |
| `terminal` | [#381](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/381) | fix(ingest): run the washout-history bridge in the nightly (retro marks were 0) | `claude/washout-history-pull` | 2026-08-10T15:10:17Z |
| `terminal` | [#380](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/380) | feat(options): export filtered Tape as safe CSV | `claude/options-tape-csv-export-20260810` | 2026-08-10T15:05:50Z |
| `terminal` | [#379](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/379) | fix(chart): revive marker tooltips — hit-tested markers, drag-safe (5 shipped tooltips rendered to nobody) | `claude/marker-tooltip-revival` | 2026-08-10T14:22:32Z |
| `terminal` | [#378](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/378) | feat(oracle): keeper reclaim waiver + notch 20 + retro projection (era gc_v2_wo2) | `claude/reclaim-waiver-keeper` | 2026-08-10T12:43:23Z |
| `terminal` | [#377](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/377) | feat(chart): make price-axis zoom smooth and unbounded | `claude/buttery-y-axis-zoom-20260810` | 2026-08-10T11:23:41Z |
| `terminal` | [#376](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/376) | feat(oracle): live washout-override enter mask + gc_v2_wo1 signal-era fence | `claude/washout-override-live-mask` | 2026-08-10T10:42:33Z |
| `terminal` | [#375](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/375) | feat(oracle): washout-override display class + forward ledger for ratified blocked entries | `claude/washout-override-display` | 2026-08-10T09:25:28Z |
| `terminal` | [#374](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/374) | feat(terminal): show live quotes in mobile search watchlist | `claude/mobile-search-live-quotes-20260809` | 2026-08-10T05:15:19Z |
| `terminal` | [#363](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/363) | feat(terminal): live second bars with reactive candle updates | `claude/live-rt-second-bars` | 2026-08-10T03:25:56Z |
| `terminal` | [#373](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/373) | feat(options): add private operator Issue Desk lane | `claude/options-issue-desk-r62-20260809` | 2026-08-10T02:08:58Z |
| `terminal` | [#371](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/371) | feat(options): add responsive Options Alpha shadow lane | `claude/options-prophet-foundation-20260808` | 2026-08-09T07:50:07Z |
| `terminal` | [#372](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/372) | test(terminal): settle the two dodge/maximize e2e assertions instead of racing them | `claude/e2e-dodge-settle-20260808` | 2026-08-09T06:34:07Z |
| `terminal` | [#369](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/369) | ci: add fail-closed merge-on-green controller | `claude/merge-on-green` | 2026-08-09T02:58:25Z |
| `terminal` | [#368](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/368) | feat(terminal): reconcile and ship the Levels gamma weather map | `claude/reconcile-levels-board` | 2026-08-09T02:40:17Z |
| `terminal` | [#366](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/366) | Upgrade Oracle and Research Desk state gradients | `claude/oracle-gradient-upgrade` | 2026-08-09T01:27:09Z |
| `terminal` | [#364](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/364) | feat(financials): deep statement history from Massive (17y AAPL), revenue history tab, and two live-data defect fixes | `claude/massive-financials` | 2026-08-09T01:26:54Z |
| `terminal` | [#358](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/358) | docs(terminal): Company Intelligence v2 delta spec + reference compositions (R0-D) | `claude/r0d-terminal-v2-delta-spec` | 2026-08-09T01:26:37Z |
| `terminal` | [#367](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/367) | fix(terminal): make dense chrome width-aware | `claude/responsive-terminal-chrome-20260808` | 2026-08-08T23:36:08Z |
| `terminal` | [#365](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/365) | fix(oracle): truth-in-labeling — structure stops, blocked setups, PIT prices (HK-O1) | `claude/hk-o1-truth-labeling` | 2026-08-08T11:11:34Z |
| `terminal` | [#362](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/362) | feat(options): SPCX in the options root picker | `claude/spcx-terminal-options-e4d44c` | 2026-08-08T05:30:45Z |
| `terminal` | [#361](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/361) | fix(shell+chart): today's volume and today's candle, not last night's | `claude/topbar-volume-live` | 2026-08-07T21:58:22Z |
| `terminal` | [#360](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/360) | fix(quotes): serve today's session, not last night's manifest (SKY 91.52 → 94.66) | `claude/ticker-price-change-bug-728df9` | 2026-08-07T21:28:56Z |
| `terminal` | [#359](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/359) | i18n(zh): natural Chinese in the Terminal, and translate what was never localised | `claude/terminal-zh` | 2026-08-07T06:09:19Z |
| `terminal` | [#356](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/356) | fix: three operator-reported bugs — crosshair label hidden, no-data symbol keeping the last chart, clipped add-to-list picker | `claude/crosshair-price-label-visibility-f5b008` | 2026-08-06T06:58:55Z |
| `terminal` | [#357](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/357) | feat(card): weekly washout-turn dual-read row beside the Oracle/Desk verdicts | `claude/washout-turn-chip` | 2026-08-06T06:03:55Z |
| `terminal` | [#355](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/355) | fix(chart): snapshot header ticker + HK intraday session bars | `claude/chinese-ticker-screenshot-bug-21e787` | 2026-08-05T02:37:24Z |
| `terminal` | [#354](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/354) | fix(chart): indicator directional colors follow the Up/Down setting | `claude/stoch-rsi-color-settings-cc3a90` | 2026-08-05T01:43:22Z |
| `terminal` | [#353](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/353) | Fix chart right-side buffer on ticker load | `claude/chart-right-buffer` | 2026-08-04T01:52:11Z |
| `terminal` | [#352](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/352) | Fix regular and after-hours price baselines after daily roll | `claude/fix-extended-hours-price-baselines` | 2026-08-03T23:24:32Z |
| `terminal` | [#351](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/351) | Fix chart reset viewport normalization | `claude/reset-chart-view-normalize-20260803` | 2026-08-03T13:37:24Z |
| `terminal` | [#350](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/350) | fix(surface): archived-session honesty, stale-root guards, repaint audit (review fixes for #346) | `claude/surface-granularity-fixes-20260803` | 2026-08-03T11:56:34Z |
| `terminal` | [#349](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/349) | fix(options): /options?tab= deep-links seed synchronously (kill the flaky post-mount hop) | `claude/vibrant-banach-e481e2` | 2026-08-03T08:18:05Z |
| `terminal` | [#347](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/347) | fix(options): Exposure desk content collapsed to 0px on phones/tablets | `claude/eloquent-allen-ed782a` | 2026-08-03T07:56:36Z |
| `terminal` | [#346](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/346) | feat(surface): percentile-normalized field + level/regime/OIΔ overlays (kill the bland) | `claude/surface-granularity-20260803` | 2026-08-03T07:31:46Z |
| `terminal` | [#344](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/344) | feat(options): §5.3 — merge PRISM into Exposure (matrix view + confluence + heat-seeker), retire the PRISM tab | `claude/prism-exposure-merge-20260803` | 2026-08-03T07:27:23Z |
| `terminal` | [#345](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/345) | Washout-bottom visibility: blocked-entry verdict, CN desk parity, washout-reversal prereg + evidence | `claude/shandong-gold-signal-blocking-2147c5` | 2026-08-03T07:01:57Z |
| `terminal` | — | _Window truncated at the most recent 50 PRs._ | — | — |
| `mastermind` | [#17](https://github.com/mastermindx-market-intelligence/Mastermind/pull/17) | docs: replace stale Phase 0 orientation | `codex/readme-orientation-20260811` | 2026-08-11T12:15:35Z |
| `mastermind` | [#16](https://github.com/mastermindx-market-intelligence/Mastermind/pull/16) | org-migration: repoint macro submodule + refresh remote to the org | `claude/org-migration-refs` | 2026-08-11T11:37:55Z |
| `mastermind` | [#14](https://github.com/mastermindx-market-intelligence/Mastermind/pull/14) | privacy: whitelist-project public snapshot positions (RUL-CL-6b) | `claude/snapshot-privacy-7386b8` | 2026-08-02T00:40:31Z |
| `mastermind` | [#13](https://github.com/mastermindx-market-intelligence/Mastermind/pull/13) | Use native benchmarks for regional books | `codex/native-market-benchmarks-20260730` | 2026-07-31T03:21:46Z |
| `mastermind` | [#12](https://github.com/mastermindx-market-intelligence/Mastermind/pull/12) | Speed up critical portfolio paint | `codex/critical-first-paint-20260730` | 2026-07-31T02:35:52Z |
| `mastermind` | [#11](https://github.com/mastermindx-market-intelligence/Mastermind/pull/11) | Add session-aware live portfolio marks and faster cold loading | `codex/initial-load-live-marks-20260730` | 2026-07-31T02:19:04Z |
| `mastermind` | [#10](https://github.com/mastermindx-market-intelligence/Mastermind/pull/10) | perf(ui): accelerate dashboard navigation | `codex/dashboard-navigation-performance-20260730` | 2026-07-31T01:23:29Z |
| `mastermind` | [#9](https://github.com/mastermindx-market-intelligence/Mastermind/pull/9) | Make the Mastermind site fully responsive | `codex/mobile-readiness-019fb582` | 2026-07-31T00:34:01Z |
| `mastermind` | [#8](https://github.com/mastermindx-market-intelligence/Mastermind/pull/8) | Name archived KRE portfolio trades | `codex/historical-etf-name-019fb567` | 2026-07-31T00:29:07Z |
| `mastermind` | [#7](https://github.com/mastermindx-market-intelligence/Mastermind/pull/7) | Fix remaining US security-name gaps | `codex/security-name-fallbacks-019fb567` | 2026-07-31T00:24:24Z |
| `mastermind` | [#6](https://github.com/mastermindx-market-intelligence/Mastermind/pull/6) | fix(ui): make brain summaries adapt to available space | `codex/adaptive-card-summary-019fb582` | 2026-07-31T00:18:27Z |
| `mastermind` | [#3](https://github.com/mastermindx-market-intelligence/Mastermind/pull/3) | Show security names across every portfolio | `codex/china-names-019fb567` | 2026-07-31T00:14:37Z |
| `mastermind` | [#5](https://github.com/mastermindx-market-intelligence/Mastermind/pull/5) | Add precise Macro context adapters to Market View | `codex/market-view-context-precision-20260730` | 2026-07-31T00:12:51Z |
| `mastermind` | [#4](https://github.com/mastermindx-market-intelligence/Mastermind/pull/4) | Fix CI package installation | `codex/fix-ci-packaging-20260730` | 2026-07-31T00:06:56Z |
| `mastermind` | [#1](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1) | Recover and validate current Mastermind application build | `codex/recover-current-workspace-20260730` | 2026-07-30T23:57:29Z |
| `mastermind` | [#2](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2) | Enforce isolated PR workflow and clean VPS releases | `codex/github-collaboration-workflow` | 2026-07-30T23:49:47Z |

---

**Advisory only.** This artifact informs coordination; no CI, merge, deploy, runtime, or semantic-authority gate consumes it. Dependency status is limited to open PRs and the displayed recent-merge window.
